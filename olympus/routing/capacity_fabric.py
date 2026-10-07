"""Persistent capacity fabric for OLYMPUS model/provider routing.

This module turns transient provider failures into routing state.  It is
intentionally provider-agnostic: adapters report typed execution results and
the fabric records successes, latency, cooldowns, and qualification evidence.
No credential value is ever persisted here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import json
import math
import os
import re
import tempfile
import time
from typing import Iterable, Optional

from olympus.routing.interfaces import RoutingExecutionResult
from olympus.routing.provider_fabric import split_provider_route

_SCHEMA_VERSION = 1
_LOCK = RLock()


def _now() -> float:
    return time.time()


def _state_path() -> Path:
    configured = os.environ.get("OLYMPUS_CAPACITY_STATE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    # /repo/olympus/routing/capacity_fabric.py -> /repo/.olympus/runtime/...
    return Path(__file__).resolve().parents[2] / ".olympus" / "runtime" / "capacity-fabric.json"


def _empty_state() -> dict:
    return {"version": _SCHEMA_VERSION, "updated_at": 0.0, "providers": {}, "routes": {}}


def _load() -> dict:
    path = _state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    data.setdefault("version", _SCHEMA_VERSION)
    data.setdefault("providers", {})
    data.setdefault("routes", {})
    return data


def _save(data: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = _SCHEMA_VERSION
    data["updated_at"] = _now()
    encoded = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".capacity-fabric-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _route_key(provider: str, route_id: str) -> str:
    return "%s::%s" % (str(provider or "unknown").strip().lower(), str(route_id or "").strip())


def _safe_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _retry_after_from_error(error: str) -> Optional[float]:
    text = str(error or "")
    patterns = (
        r"retry[- ]after\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s|sec|secs|seconds|m|min|mins|minutes)?",
        r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s|sec|secs|seconds|m|min|mins|minutes)?",
        r"reset after\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s|sec|secs|seconds|m|min|mins|minutes)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = float(match.group(1))
        unit = (match.group(2) or "s").lower()
        if unit == "ms":
            value /= 1000.0
        elif unit.startswith("m"):
            value *= 60.0
        return max(0.0, value)
    return None


def _provider_wide(error: str, status: str) -> bool:
    text = (str(error or "") + " " + str(status or "")).lower()
    return any(token in text for token in (
        "daily quota", "daily limit", "requests per day", "free-models-per-day",
        "tokens per minute", "requests per minute", "input tokens per minute",
        "output tokens per minute", "authentication_error", "invalid_api_key",
        "invalid api key", "billing_error", "payment required", "unauthorized",
        "forbidden", "account quota", "account limit",
    ))


def _route_state(entry: dict, now: Optional[float] = None) -> str:
    now = _now() if now is None else now
    if entry.get("quarantined"):
        return "quarantined"
    until = float(entry.get("cooldown_until") or 0.0)
    if until > now:
        return "cooldown"
    if int(entry.get("success_count") or 0) > 0:
        return "ready" if int(entry.get("failure_streak") or 0) == 0 else "degraded"
    return "candidate"


def _provider_state(entry: dict, now: Optional[float] = None) -> str:
    now = _now() if now is None else now
    until = float(entry.get("cooldown_until") or 0.0)
    if until > now:
        return "cooldown"
    if int(entry.get("success_count") or 0) > 0:
        return "ready" if int(entry.get("failure_streak") or 0) == 0 else "degraded"
    return "candidate"


def _latency_ewma(old: Optional[float], current: int) -> float:
    if not old:
        return float(max(1, current))
    return round((0.75 * float(old)) + (0.25 * max(1, int(current))), 2)


@dataclass(frozen=True)
class CapacityDecision:
    eligible: bool
    state: str
    reason: str = ""
    cooldown_until: float = 0.0


class CapacityFabric:
    """Persistent model/provider health, qualification and circuit-breaker state."""

    def _mutate(self, fn):
        with _LOCK:
            data = _load()
            result = fn(data)
            _save(data)
            return result

    def snapshot(self) -> dict:
        with _LOCK:
            data = _load()
        now = _now()
        providers = []
        for provider_id, entry in sorted((data.get("providers") or {}).items()):
            row = dict(entry)
            row.update({"id": provider_id, "state": _provider_state(entry, now)})
            providers.append(row)
        routes = []
        for key, entry in sorted((data.get("routes") or {}).items()):
            row = dict(entry)
            row.update({"key": key, "state": _route_state(entry, now)})
            routes.append(row)
        counts = {
            state: sum(1 for row in routes if row["state"] == state)
            for state in ("ready", "candidate", "degraded", "cooldown", "quarantined")
        }
        return {
            "version": data.get("version", _SCHEMA_VERSION),
            "updated_at": data.get("updated_at", 0.0),
            "counts": counts,
            "providers": providers,
            "routes": routes,
        }

    def decision(self, route_id: str, provider_hint: Optional[str] = None) -> CapacityDecision:
        provider = str(provider_hint or "").strip().lower()
        if not provider:
            provider, _ = split_provider_route(route_id, "omniroute")
            provider = provider.lower()
        with _LOCK:
            data = _load()
        now = _now()
        provider_entry = (data.get("providers") or {}).get(provider, {})
        provider_until = float(provider_entry.get("cooldown_until") or 0.0)
        if provider_until > now:
            return CapacityDecision(False, "cooldown", "provider_circuit_open", provider_until)
        key = _route_key(provider, route_id)
        entry = (data.get("routes") or {}).get(key, {})
        state = _route_state(entry, now)
        if state == "quarantined":
            return CapacityDecision(False, state, str(entry.get("quarantine_reason") or "route_quarantined"), 0.0)
        route_until = float(entry.get("cooldown_until") or 0.0)
        if route_until > now:
            return CapacityDecision(False, "cooldown", "model_circuit_open", route_until)
        return CapacityDecision(True, state)

    def route_rank(self, route_id: str, provider_hint: Optional[str] = None) -> tuple:
        decision = self.decision(route_id, provider_hint)
        with _LOCK:
            data = _load()
        provider = str(provider_hint or "").strip().lower()
        if not provider:
            provider, _ = split_provider_route(route_id, "omniroute")
            provider = provider.lower()
        entry = (data.get("routes") or {}).get(_route_key(provider, route_id), {})
        state_order = {"ready": 0, "candidate": 1, "degraded": 2, "cooldown": 3, "quarantined": 4}
        success = int(entry.get("success_count") or 0)
        failure = int(entry.get("failure_count") or 0)
        total = success + failure
        success_rate = success / total if total else 0.5
        latency = float(entry.get("latency_ewma_ms") or 999999.0)
        return (state_order.get(decision.state, 9), -success_rate, latency)

    def observe(self, route_id: str, result: RoutingExecutionResult, provider_hint: Optional[str] = None) -> dict:
        provider = str(provider_hint or getattr(result, "provider", "") or "").strip().lower()
        if not provider:
            provider, _ = split_provider_route(route_id, "omniroute")
            provider = provider.lower()
        status = str(getattr(result, "status", "") or ("success" if result.success else "technical_failure"))
        error = str(getattr(result, "error", "") or "")
        latency = max(1, int(getattr(result, "latency_ms", 0) or 1))
        actual_model = str(getattr(result, "actual_model", "") or "")
        now = _now()

        def apply(data):
            providers = data.setdefault("providers", {})
            routes = data.setdefault("routes", {})
            p = providers.setdefault(provider, {})
            r = routes.setdefault(_route_key(provider, route_id), {
                "provider": provider,
                "route_id": route_id,
            })
            r["last_seen"] = now
            r["last_status"] = status
            r["last_error"] = error[:2000] if error else None
            r["actual_model"] = actual_model or r.get("actual_model")
            r["latency_ewma_ms"] = _latency_ewma(r.get("latency_ewma_ms"), latency)
            p["last_seen"] = now
            p["last_status"] = status
            p["latency_ewma_ms"] = _latency_ewma(p.get("latency_ewma_ms"), latency)

            if result.success:
                for entry in (p, r):
                    entry["success_count"] = int(entry.get("success_count") or 0) + 1
                    entry["failure_streak"] = 0
                    entry["last_success"] = now
                    entry["cooldown_until"] = 0.0
                return {"provider": provider, "route_id": route_id, "state": "ready"}

            p["failure_count"] = int(p.get("failure_count") or 0) + 1
            r["failure_count"] = int(r.get("failure_count") or 0) + 1
            p["failure_streak"] = int(p.get("failure_streak") or 0) + 1
            r["failure_streak"] = int(r.get("failure_streak") or 0) + 1
            p["last_failure"] = now
            r["last_failure"] = now

            normalized = (status + " " + error).lower()
            if "rate_limited" in normalized or "rate limit" in normalized or "cooling down" in normalized or "429" in normalized:
                base = _safe_int_env("OLYMPUS_MODEL_COOLDOWN_SECONDS", 120, 15, 3600)
                retry_after = _retry_after_from_error(error)
                # Repeated rate limits grow the quarantine window without turning
                # a temporary quota event into a permanent model failure.
                exponent = min(4, max(0, int(r.get("failure_streak") or 1) - 1))
                delay = max(float(base * (2 ** exponent)), float(retry_after or 0.0))
                r["cooldown_until"] = now + min(delay, 3600.0)
                r["cooldown_reason"] = "rate_limited"
                r["rate_limit_count"] = int(r.get("rate_limit_count") or 0) + 1
                if _provider_wide(error, status):
                    pdelay = max(delay, float(_safe_int_env("OLYMPUS_PROVIDER_COOLDOWN_SECONDS", 180, 30, 7200)))
                    p["cooldown_until"] = now + min(pdelay, 7200.0)
                    p["cooldown_reason"] = "provider_rate_limited"
                    p["rate_limit_count"] = int(p.get("rate_limit_count") or 0) + 1
            elif "timeout" in normalized or "timed out" in normalized:
                r["timeout_count"] = int(r.get("timeout_count") or 0) + 1
                threshold = _safe_int_env("OLYMPUS_TIMEOUT_CIRCUIT_THRESHOLD", 2, 1, 10)
                if int(r["timeout_count"]) >= threshold:
                    delay = _safe_int_env("OLYMPUS_TIMEOUT_COOLDOWN_SECONDS", 90, 15, 1800)
                    r["cooldown_until"] = now + delay
                    r["cooldown_reason"] = "repeated_timeout"
            elif any(token in normalized for token in ("unavailable", "model_not_found", "model not found", "404")):
                r["cooldown_until"] = now + _safe_int_env("OLYMPUS_UNAVAILABLE_COOLDOWN_SECONDS", 1800, 60, 86400)
                r["cooldown_reason"] = "model_unavailable"
            elif any(token in normalized for token in ("authentication_error", "invalid api key", "invalid_api_key", "unauthorized", "forbidden")):
                p["cooldown_until"] = now + _safe_int_env("OLYMPUS_AUTH_COOLDOWN_SECONDS", 1800, 60, 86400)
                p["cooldown_reason"] = "authentication_error"
            return {"provider": provider, "route_id": route_id, "state": _route_state(r, now)}

        return self._mutate(apply)

    def record_probe(self, provider: str, route_id: str, probe: str, ok: bool, *, latency_ms: int = 0, error: str = "") -> dict:
        provider = str(provider or "").strip().lower()
        route_id = str(route_id or "").strip()
        now = _now()

        def apply(data):
            routes = data.setdefault("routes", {})
            r = routes.setdefault(_route_key(provider, route_id), {"provider": provider, "route_id": route_id})
            probes = r.setdefault("probes", {})
            probes[str(probe)] = {"ok": bool(ok), "at": now, "latency_ms": int(latency_ms or 0), "error": str(error or "")[:1000] or None}
            required = (
                "response",
                "action_protocol",
                "code_action",
                "patch_action",
                "repair_after_verifier",
            )
            r["qualified"] = all(bool((probes.get(name) or {}).get("ok")) for name in required)
            r["last_probe"] = now
            if r["qualified"]:
                r["qualification_level"] = "agent_route_v2"
                r["quarantined"] = False
                r["quarantine_reason"] = None
            return dict(r)

        return self._mutate(apply)

    def quarantine(self, provider: str, route_id: str, reason: str) -> None:
        provider = str(provider or "").strip().lower()
        route_id = str(route_id or "").strip()
        def apply(data):
            r = data.setdefault("routes", {}).setdefault(_route_key(provider, route_id), {"provider": provider, "route_id": route_id})
            r["quarantined"] = True
            r["quarantine_reason"] = str(reason or "manual_quarantine")[:1000]
            r["quarantined_at"] = _now()
        self._mutate(apply)

    def reset(self, provider: Optional[str] = None, route_id: Optional[str] = None) -> dict:
        provider_norm = str(provider or "").strip().lower()
        route_norm = str(route_id or "").strip()
        def apply(data):
            if not provider_norm and not route_norm:
                data["providers"] = {}
                data["routes"] = {}
            elif provider_norm and route_norm:
                data.setdefault("routes", {}).pop(_route_key(provider_norm, route_norm), None)
            elif provider_norm:
                data.setdefault("providers", {}).pop(provider_norm, None)
                prefix = provider_norm + "::"
                data["routes"] = {k: v for k, v in data.setdefault("routes", {}).items() if not k.startswith(prefix)}
            return True
        self._mutate(apply)
        return self.snapshot()


class CapacityAwareRoutingAdapter:
    """Observe every model call and persist capacity evidence automatically."""

    def __init__(self, adapter, fabric: Optional[CapacityFabric] = None):
        self.adapter = adapter
        self.fabric = fabric or CapacityFabric()

    def health(self):
        return self.adapter.health()

    def list_models(self):
        return self.adapter.list_models()

    def execute(self, model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
        decision = self.fabric.decision(model_id)
        if not decision.eligible:
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="capacity-fabric",
                output="",
                latency_ms=1,
                cost=0.0,
                success=False,
                error="capacity_circuit_open: %s until %.3f" % (decision.reason or decision.state, decision.cooldown_until),
                metadata={"capacity_state": decision.state, "cooldown_until": decision.cooldown_until},
                status="rate_limited" if decision.state == "cooldown" else "unavailable",
            )
        result = self.adapter.execute(model_id, prompt, max_tokens=max_tokens, temperature=temperature, **kwargs)
        self.fabric.observe(model_id, result)
        return result


def capacity_fabric_snapshot() -> dict:
    return CapacityFabric().snapshot()


def capacity_filter_routes(routes: Iterable) -> tuple:
    """Remove open-circuit routes and prefer already-proven routes.

    Stable route priority remains the tiebreaker. This is deliberately a
    migration-friendly policy: unobserved routes are candidates, not rejected,
    so a newly configured provider can be qualified without breaking the
    existing production chain.
    """
    fabric = CapacityFabric()
    eligible = []
    for index, route in enumerate(tuple(routes)):
        provider_hint = getattr(route, "provider", None) if "::" in str(route.id) else "omniroute"
        decision = fabric.decision(route.id, provider_hint)
        if not decision.eligible:
            continue
        eligible.append((fabric.route_rank(route.id, provider_hint), index, route))
    eligible.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in eligible)
