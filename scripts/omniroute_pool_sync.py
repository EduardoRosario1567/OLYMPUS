#!/usr/bin/env python3
"""Safely discover and expand the proven OmniRoute free combo.

OLYMPUS 2.7.17 rules:
- Conding-free is always the primary route.
- Keep its existing models in their exact order.
- Discover additional OpenRouter models only when explicitly free (:free or zero/zero pricing).
- Probe every new candidate before inclusion.
- Validate a temporary candidate combo before touching Conding-free.
- Replace Conding-free transactionally only when management create/delete is proven.
- If any swap/probe step fails, recreate the original combo from its snapshot.
- Ollama local/cloud remain optional tiers and are enabled only after real probes.
- No secret value is ever written to status or logs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / ".olympus" / "runtime" / "omniroute-pools.json"
SNAPSHOT_DIR = ROOT / ".olympus" / "runtime" / "combo-snapshots"
BASE_URL = os.environ.get("OLYMPUS_OMNIROUTE_URL", "http://127.0.0.1:20128").rstrip("/")
BASELINE_COMBO = os.environ.get("OLYMPUS_PRIMARY_FREE_COMBO", "Conding-free").strip() or "Conding-free"
MAX_NEW_PROBES = int(os.environ.get("OLYMPUS_FREE_MODEL_PROBE_LIMIT", "64"))


def _strip_quotes(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def _api_key() -> str:
    for name in ("OLYMPUS_OMNIROUTE_API_KEY", "OMNIROUTE_API_KEY"):
        value = _strip_quotes(os.environ.get(name, ""))
        if value:
            return value
    for env_path in (ROOT / "backend" / ".env", ROOT / ".env"):
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        values = {}
        for line in lines:
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = _strip_quotes(value)
        for name in ("OLYMPUS_OMNIROUTE_API_KEY", "OMNIROUTE_API_KEY"):
            if values.get(name):
                return values[name]
    return ""


def _request(method: str, path: str, key: str, payload: dict | None = None, timeout: float = 12.0):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "OLYMPUS/2.7.17"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if key:
        headers["Authorization"] = "Bearer " + key
    req = Request(BASE_URL + path, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw) if raw else {}
            except ValueError:
                data = {"raw": raw}
            return response.status, data
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {"raw": raw}
        return exc.code, data
    except (URLError, OSError) as exc:
        return 0, {"error": str(exc)}


def _extract_json(text: str):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text or ""):
        try:
            value, _ = decoder.raw_decode((text or "")[match.start():])
            return value
        except ValueError:
            continue
    return None


def _combo_list():
    try:
        proc = subprocess.run(
            ["omniroute", "combo", "list", "--json"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return [], "unavailable"
    parsed = _extract_json((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if isinstance(parsed, dict) and isinstance(parsed.get("combos"), list):
        return parsed["combos"], "json"
    if isinstance(parsed, list):
        return parsed, "json"
    return [], "unparsed"

def _rows_from_payload(payload: Any) -> list[dict]:
    """Normalize model-catalog payloads from OmniRoute API/CLI variants."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = []
        for key in ("data", "models", "items", "catalog", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend(value)
        # Some OmniRoute versions group models by provider.
        for value in payload.values():
            if isinstance(value, dict):
                for nested_key in ("models", "items", "data"):
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        rows.extend(nested)
    else:
        rows = []
    normalized = []
    for item in rows:
        if isinstance(item, str):
            normalized.append({"id": item})
        elif isinstance(item, dict):
            row = dict(item)
            if not row.get("id"):
                for key in ("model", "modelId", "model_id", "name"):
                    if row.get(key):
                        row["id"] = row[key]
                        break
            normalized.append(row)
    return normalized


def _catalog_rows_api(key: str) -> list[dict]:
    code, payload = _request("GET", "/api/models/catalog", key, timeout=15)
    return _rows_from_payload(payload) if code == 200 else []


def _catalog_rows_cli(search: str = "ollama-cloud") -> list[dict]:
    commands = (
        ["omniroute", "models", "--search", search, "--json"],
        ["omniroute", "models", search, "--json"],
        ["omniroute", "models", "--json"],
    )
    for command in commands:
        try:
            proc = subprocess.run(
                command, cwd=str(ROOT), capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        parsed = _extract_json((proc.stdout or "") + "\n" + (proc.stderr or ""))
        rows = _rows_from_payload(parsed)
        if rows:
            return rows
    return []


def _configured_provider_ids() -> set[str]:
    try:
        proc = subprocess.run(
            ["omniroute", "providers", "list", "--json"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    parsed = _extract_json((proc.stdout or "") + "\n" + (proc.stderr or ""))
    rows = []
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        for key in ("providers", "connections", "data", "items"):
            if isinstance(parsed.get(key), list):
                rows.extend(parsed[key])
    result = set()
    for item in rows:
        if isinstance(item, str):
            result.add(item.lower().strip())
            continue
        if not isinstance(item, dict):
            continue
        for key in ("id", "provider", "providerId", "provider_id", "alias", "name"):
            value = item.get(key)
            if value:
                result.add(str(value).lower().strip())
    return result


def _model_id(item: Any) -> str:
    return str(item.get("id") or "").strip() if isinstance(item, dict) else ""


def _provider_hints(item: dict) -> set[str]:
    values = []
    for key in ("provider", "providerId", "provider_id", "owned_by", "owner"):
        value = item.get(key)
        if value:
            values.append(str(value).lower().strip())
    model = _model_id(item).lower()
    if "/" in model:
        values.append(model.split("/", 1)[0])
    return set(values)


def _is_openrouter_free(item: dict) -> bool:
    model = _model_id(item).lower()
    hints = _provider_hints(item)
    if not model:
        return False
    openrouter = model.startswith("openrouter/") or "openrouter" in hints
    explicit_free = model.endswith(":free") or model.endswith("/free") or "/free/" in model
    raw = item.get("pricing") if isinstance(item, dict) else None
    zero_price = False
    if isinstance(raw, dict):
        try:
            prompt = float(raw.get("prompt", raw.get("input", 1)))
            completion = float(raw.get("completion", raw.get("output", 1)))
            zero_price = prompt == 0.0 and completion == 0.0
        except (TypeError, ValueError):
            pass
    return openrouter and (explicit_free or zero_price)


def _classify_ollama(item: dict) -> str | None:
    model = _model_id(item).lower()
    hints = _provider_hints(item)
    if hints & {"ollama-cloud", "ollamacloud"} or model.startswith(("ollama-cloud/", "ollamacloud/")):
        return "cloud"
    if hints & {"ollama", "ollama-local"} or model.startswith(("ollama/", "ollama-local/")):
        return "local"
    return None


def _rank(models: list[str]) -> list[str]:
    blocked = ("embed", "embedding", "vision", "audio", "whisper", "tts", "guard")
    usable = [m for m in dict.fromkeys(models) if m and not any(x in m.lower() for x in blocked)]
    priorities = ("coder", "code", "qwen", "deepseek", "gpt-oss", "nemotron", "llama", "mistral", "gemma")
    def score(value: str):
        low = value.lower()
        return next((i for i, token in enumerate(priorities) if token in low), len(priorities)), low
    return sorted(usable, key=score)


def _combo_models(combo: dict) -> list[str]:
    return [str(row.get("model")).strip() for row in (combo.get("models") or [])
            if isinstance(row, dict) and row.get("model")]


def _probe(model: str, key: str, timeout: float = 25.0):
    status, data = _request(
        "POST", "/v1/chat/completions", key,
        {"model": model, "messages": [{"role": "user", "content": "Return only OLYMPUS_READY"}],
         "max_tokens": 24, "temperature": 0}, timeout=timeout,
    )
    if status != 200 or not isinstance(data, dict):
        return False, status, ""
    choices = data.get("choices") or []
    if not choices:
        return False, status, str(data.get("model") or "")
    content = choices[0].get("message", {}).get("content", "") if isinstance(choices[0], dict) else ""
    return bool(str(content).strip()), status, str(data.get("model") or "")


def _combo_body(name: str, models: list[str], source: dict | None = None, description: str | None = None) -> dict:
    source = source or {}
    original_rows = {str(x.get("model")): x for x in (source.get("models") or []) if isinstance(x, dict) and x.get("model")}
    rows = []
    for i, model in enumerate(models):
        if model in original_rows:
            row = dict(original_rows[model])
            row["model"] = model
            row.setdefault("kind", "model")
            row.setdefault("providerId", model.split("/", 1)[0])
            row.setdefault("weight", 0)
        else:
            safe = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")[:90]
            row = {"id": f"conding-free-model-auto-{i+1}-{safe}", "kind": "model", "model": model,
                   "providerId": model.split("/", 1)[0], "weight": 0, "label": "auto-free"}
        rows.append(row)
    config = dict(source.get("config") or {})
    config.setdefault("maxRetries", 1)
    config.setdefault("retryDelayMs", 500)
    config.setdefault("trackMetrics", True)
    return {
        "name": name,
        "description": description or str(source.get("description") or "Fallback para desenvolvimento usando somente modelos gratuitos"),
        "models": rows,
        "strategy": str(source.get("strategy") or "priority"),
        "config": config,
    }


def _create_combo(body: dict, key: str) -> tuple[bool, str]:
    # Prefer direct management API. If unavailable, use OmniRoute's generated POST command.
    code, data = _request("POST", "/api/combos", key, body, timeout=20)
    if code in (200, 201):
        return True, "api"
    env = dict(os.environ)
    if key:
        env["OMNIROUTE_API_KEY"] = key
    try:
        proc = subprocess.run(
            ["omniroute", "api", "combos", "post-api-combos", "--body", json.dumps(body, separators=(",", ":"))],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30, check=False, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return False, f"http_{code or 0}"
    return proc.returncode == 0, "cli" if proc.returncode == 0 else f"http_{code or 0}_cli_failed"


def _delete_combo(combo_id: str, key: str) -> tuple[bool, int]:
    if not combo_id:
        return False, 0
    code, _ = _request("DELETE", "/api/combos/" + quote(combo_id, safe=""), key, timeout=15)
    return code in (200, 204), code


def _find_combo(name: str) -> dict | None:
    combos, _ = _combo_list()
    return next((x for x in combos if isinstance(x, dict) and str(x.get("name")) == name), None)


def _snapshot(combo: dict) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / ("Conding-free-before-" + time.strftime("%Y%m%d_%H%M%S") + ".json")
    path.write_text(json.dumps(combo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _probe_new_models(candidates: list[str], key: str, timeout: float) -> tuple[list[str], dict[str, int]]:
    ready, codes = [], {}
    for model in candidates[:MAX_NEW_PROBES]:
        ok, code, _ = _probe(model, key, timeout=timeout)
        codes[model] = code
        if ok:
            ready.append(model)
    return ready, codes


def _transactional_expand(baseline: dict, expanded_models: list[str], key: str, status: dict) -> bool:
    baseline_models = _combo_models(baseline)
    if expanded_models == baseline_models:
        status["baseline_update"] = "already_maximized"
        return True
    stamp = time.strftime("%Y%m%d%H%M%S")
    candidate_name = f"Conding-free-candidate-{stamp}"
    backup_name = f"Conding-free-backup-{stamp}"
    candidate_body = _combo_body(candidate_name, expanded_models, baseline, "OLYMPUS validated candidate for Conding-free expansion")
    backup_body = _combo_body(backup_name, baseline_models, baseline, "Automatic rollback copy of Conding-free")
    original_body = _combo_body(BASELINE_COMBO, baseline_models, baseline)
    expanded_body = _combo_body(BASELINE_COMBO, expanded_models, baseline)

    created, via = _create_combo(candidate_body, key)
    status["candidate_create"] = via
    if not created:
        status["baseline_update"] = "candidate_create_failed"
        return False
    candidate = _find_combo(candidate_name)
    ok, http, _ = _probe(candidate_name, key, timeout=30)
    status["candidate_probe_http"] = http
    if not ok:
        if candidate:
            _delete_combo(str(candidate.get("id") or ""), key)
        status["baseline_update"] = "candidate_probe_failed"
        return False

    # Prove both create and delete management capabilities before touching baseline.
    backup_created, backup_via = _create_combo(backup_body, key)
    status["backup_create"] = backup_via
    backup = _find_combo(backup_name) if backup_created else None
    if not backup_created or not backup:
        if candidate:
            _delete_combo(str(candidate.get("id") or ""), key)
        status["baseline_update"] = "management_backup_failed"
        return False

    original_id = str(baseline.get("id") or "")
    if not original_id:
        _delete_combo(str(backup.get("id") or ""), key)
        if candidate:
            _delete_combo(str(candidate.get("id") or ""), key)
        status["baseline_update"] = "baseline_id_missing"
        return False

    deleted, delete_http = _delete_combo(original_id, key)
    status["baseline_delete_http"] = delete_http
    if not deleted:
        _delete_combo(str(backup.get("id") or ""), key)
        if candidate:
            _delete_combo(str(candidate.get("id") or ""), key)
        status["baseline_update"] = "baseline_delete_failed"
        return False

    created_new, created_via = _create_combo(expanded_body, key)
    status["baseline_recreate"] = created_via
    final_ok = False
    if created_new:
        final_ok, final_http, final_actual = _probe(BASELINE_COMBO, key, timeout=35)
        status["baseline_final_probe_http"] = final_http
        status["baseline_final_actual_model"] = final_actual
    if final_ok:
        # Successful swap: cleanup temporary candidate and backup.
        current_candidate = _find_combo(candidate_name)
        current_backup = _find_combo(backup_name)
        if current_candidate:
            _delete_combo(str(current_candidate.get("id") or ""), key)
        if current_backup:
            _delete_combo(str(current_backup.get("id") or ""), key)
        status["baseline_update"] = "expanded_and_verified"
        return True

    # Rollback: remove any broken replacement and recreate original snapshot.
    broken = _find_combo(BASELINE_COMBO)
    if broken:
        _delete_combo(str(broken.get("id") or ""), key)
    restored, restore_via = _create_combo(original_body, key)
    status["rollback_recreate"] = restore_via
    restore_ok = False
    if restored:
        restore_ok, restore_http, _ = _probe(BASELINE_COMBO, key, timeout=35)
        status["rollback_probe_http"] = restore_http
    if restore_ok:
        for temp_name in (candidate_name, backup_name):
            temp = _find_combo(temp_name)
            if temp:
                _delete_combo(str(temp.get("id") or ""), key)
        status["baseline_update"] = "rolled_back"
    else:
        # Emergency backup combo intentionally remains available for manual recovery.
        status["baseline_update"] = "rollback_failed_backup_preserved"
    return False


def _write_status(data: dict):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATUS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, STATUS_PATH)


def run(full: bool = True) -> dict:
    key = _api_key()
    status: dict[str, Any] = {
        "version": 2, "updated_at": int(time.time()), "state": "baseline_only",
        "baseline_combo": BASELINE_COMBO, "primary_combo": BASELINE_COMBO,
        "primary_combo_ready": False, "baseline_update": "not_attempted",
        "openrouter_free_discovered": 0, "openrouter_new_probe_ready": [],
        "ollama_local_models": [], "ollama_cloud_models": [],
        "ollama_local_ready": [], "ollama_cloud_ready": [], "endpoint_http": None, "reason": "",
    }
    http, payload = _request("GET", "/v1/models", key, timeout=8)
    status["endpoint_http"] = http
    if http != 200 or not isinstance(payload, dict):
        status["reason"] = "OmniRoute /v1/models unavailable or unauthorized"
        _write_status(status); return status

    rows = [row for row in _rows_from_payload(payload) if _model_id(row)]
    free_models = _rank([_model_id(row) for row in rows if _is_openrouter_free(row)])
    local_models = _rank([_model_id(row) for row in rows if _classify_ollama(row) == "local"])

    # Ollama Cloud is a first-class OmniRoute provider. /v1/models can omit
    # provider catalogs that are configured but not part of the current route,
    # so consult the management catalog and CLI as additional discovery sources.
    cloud_rows = list(rows)
    cloud_rows.extend(_catalog_rows_api(key))
    cloud_rows.extend(_catalog_rows_cli("ollama-cloud"))
    cloud_models = _rank([_model_id(row) for row in cloud_rows if _classify_ollama(row) == "cloud"])
    configured_ids = _configured_provider_ids()
    cloud_provider_configured = bool(
        configured_ids & {"ollama-cloud", "ollamacloud", "ollama cloud"}
        or any(_classify_ollama(row) == "cloud" for row in rows)
    )
    status["ollama_cloud_provider_configured"] = cloud_provider_configured
    status["ollama_cloud_discovery_sources"] = {
        "v1_models": len([row for row in rows if _classify_ollama(row) == "cloud"]),
        "catalog_or_cli": max(0, len(cloud_models)),
    }
    status["openrouter_free_discovered"] = len(free_models)
    status["ollama_local_models"] = local_models[:100]
    status["ollama_cloud_models"] = cloud_models[:100]

    baseline_ok, baseline_http, baseline_actual = _probe(BASELINE_COMBO, key, timeout=25 if full else 10)
    status["baseline_probe_http"] = baseline_http
    status["baseline_actual_model"] = baseline_actual
    status["primary_combo_ready"] = baseline_ok
    if not baseline_ok:
        status["state"] = "degraded"
        status["reason"] = "Known-good Conding-free probe failed; no mutation allowed"
        _write_status(status); return status

    combos, parser = _combo_list()
    status["combo_parser"] = parser
    baseline = next((x for x in combos if isinstance(x, dict) and str(x.get("name")) == BASELINE_COMBO), None)
    if not baseline:
        status["reason"] = "Conding-free exists as runtime route but could not be snapshotted; mutation disabled"
    else:
        baseline_models = _combo_models(baseline)
        status["baseline_model_count_before"] = len(baseline_models)
        new_candidates = [m for m in free_models if m not in set(baseline_models)]
        if full and new_candidates:
            ready_new, probe_codes = _probe_new_models(new_candidates, key, timeout=12)
            status["openrouter_new_probe_ready"] = ready_new
            status["openrouter_new_probe_http"] = probe_codes
            expanded = list(dict.fromkeys(baseline_models + ready_new))
            status["expanded_candidate_count"] = len(expanded)
            snapshot = _snapshot(baseline)
            status["baseline_snapshot"] = str(snapshot.relative_to(ROOT))
            _transactional_expand(baseline, expanded, key, status)
        elif full:
            status["baseline_update"] = "already_maximized"
            status["expanded_candidate_count"] = len(baseline_models)

    # Optional Ollama tiers. Their failure can never remove Conding-free.
    for model in (local_models[:3] if full else local_models[:1]):
        ok, code, actual = _probe(model, key, timeout=20 if full else 8)
        if ok:
            status["ollama_local_ready"].append(model)
            status["ollama_local_probe_http"] = code
            status["ollama_local_actual_model"] = actual
            break
    cloud_probe_codes = {}
    for model in (cloud_models[:8] if full else cloud_models[:2]):
        ok, code, actual = _probe(model, key, timeout=25 if full else 10)
        cloud_probe_codes[model] = code
        if ok:
            status["ollama_cloud_ready"].append(model)
            status["ollama_cloud_probe_http"] = code
            status["ollama_cloud_actual_model"] = actual
            break
    if cloud_probe_codes:
        status["ollama_cloud_probe_codes"] = cloud_probe_codes
    if status["ollama_cloud_ready"]:
        # A successful inference through the gateway is stronger evidence than
        # CLI metadata: the provider is effectively configured and usable.
        status["ollama_cloud_provider_configured"] = True
        status["ollama_cloud_reason"] = "ready_via_omniroute"
    elif cloud_models:
        status["ollama_cloud_reason"] = "models_discovered_but_live_probe_failed"
    elif status.get("ollama_cloud_provider_configured"):
        status["ollama_cloud_reason"] = "provider_configured_but_no_models_discovered"
    else:
        status["ollama_cloud_reason"] = "provider_not_configured_in_omniroute"

    # Re-probe the baseline after any attempted mutation; if it does not answer, report degraded.
    final_ok, final_http, final_actual = _probe(BASELINE_COMBO, key, timeout=20 if full else 8)
    status["baseline_postsync_probe_http"] = final_http
    status["baseline_postsync_actual_model"] = final_actual
    status["primary_combo_ready"] = final_ok
    status["state"] = "ready" if final_ok else "degraded"
    status["reason"] = (
        "Conding-free preserved as primary; free expansion is transactional; Ollama tiers require successful probes"
        if final_ok else "Conding-free post-sync probe failed"
    )
    _write_status(status)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="refresh readiness without mutating Conding-free")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run(full=not args.quick)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("OmniRoute pools:", result.get("state"))
        print("Primary free combo:", result.get("primary_combo"))
        print("OpenRouter free discovered:", result.get("openrouter_free_discovered"))
        print("New free models validated:", len(result.get("openrouter_new_probe_ready", [])))
        print("Conding-free update:", result.get("baseline_update"))
        print("Ollama local ready:", len(result.get("ollama_local_ready", [])))
        print("Ollama Cloud ready:", len(result.get("ollama_cloud_ready", [])))
    return 0 if result.get("primary_combo_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
