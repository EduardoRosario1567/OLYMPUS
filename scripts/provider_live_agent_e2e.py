#!/usr/bin/env python3
"""Live isolated coding-agent proof for one configured provider.

This command never changes provider preferences and never enables automatic
fallback. It executes one tiny real AgentLoop workspace against one provider
model and exits non-zero unless the model repairs the requested deliverable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from dotenv import load_dotenv

load_dotenv(ROOT / "backend" / ".env", override=False)

from app.core.provider_runtime import build_provider_registry, _rank_live_models
from olympus.agent.action_normalizer import normalize_action_text
from olympus.agent.actions import ActionType
from olympus.agent.loop import AgentLoop
from olympus.agent.planner import ModelPlanner
from olympus.agent.state import AgentState
from olympus.agent.verifier import AgentVerifier
from olympus.routing.capacity_fabric import CapacityFabric
from olympus.routing.provider_fabric import provider_route_id


ALLOWED_PROVIDERS = {"together", "ollama_cloud"}
TASK = (
    "Repair the existing app/index.html. The final document must contain one "
    "semantic <main>, one <h1>OLYMPUS QUALIFICATION</h1>, and an element with "
    'data-status="ready". Preserve a complete valid HTML document. Do not create '
    "other files. Verify the repair and finish."
)
INITIAL_HTML = (
    "<!doctype html><html><head><meta charset=\"utf-8\"><title>Probe</title></head>"
    "<body><div>OLYMPUS QUALIFICATION</div></body></html>"
)


def validate_html(text: str) -> tuple[bool, list[str]]:
    value = str(text or "")
    lower = value.lower()
    failures = []
    if "<main" not in lower or "</main>" not in lower:
        failures.append("missing semantic main")
    if "<h1>olympus qualification</h1>" not in lower:
        failures.append("missing required h1")
    if 'data-status="ready"' not in lower and "data-status='ready'" not in lower:
        failures.append("missing ready status")
    if "<html" not in lower or "</html>" not in lower:
        failures.append("incomplete html document")
    return not failures, failures


class QualificationVerifier(AgentVerifier):
    """Verifier that makes the live qualification contract authoritative."""

    def verify_task_deliverable(self, task, files_modified, active_skills=()):
        base = tuple(super().verify_task_deliverable(task, files_modified, active_skills))
        target = self.root / "app" / "index.html"
        try:
            source = target.read_text(encoding="utf-8")
        except OSError:
            return tuple(dict.fromkeys(base + ("qualification: app/index.html is missing",)))
        valid, failures = validate_html(source)
        qualification = tuple("qualification: %s" % item for item in failures)
        return tuple(dict.fromkeys(base + qualification))


def choose_models(adapter, requested: str | None) -> list[str]:
    rows = [row.model_id for row in adapter.list_models() if getattr(row, "available", True)]
    if requested:
        return [requested] if requested in rows else []
    return list(_rank_live_models(tuple(rows)))[:3]


def qualify_ready_agent(provider: str, model: str, adapter) -> dict:
    route_id = provider_route_id(provider, model)
    fabric = CapacityFabric()
    probes = (
        ("response",
         '{"type":"finish","target":null,"payload":null,"reason":"OLYMPUS_PROBE_OK"}',
         lambda action: action.type == ActionType.FINISH and action.target is None),
        ("action_protocol",
         '{"type":"finish","target":null,"payload":null,"reason":"structured action protocol ok"}',
         lambda action: action.type == ActionType.FINISH and action.target is None),
        ("code_action",
         '{"type":"create_file","target":"qualification_probe.txt","payload":"OLYMPUS_PROBE_OK","reason":"qualification"}',
         lambda action: action.type == ActionType.CREATE_FILE and action.target == "qualification_probe.txt"
         and str(action.payload) == "OLYMPUS_PROBE_OK"),
        ("patch_action",
         'A file qualification_probe.txt contains exactly OLYMPUS_PROBE_OLD. Return only one patch_file action for that file using payload {"old_text":"OLYMPUS_PROBE_OLD","new_text":"OLYMPUS_PROBE_OK"}.',
         lambda action: action.type == ActionType.PATCH_FILE and action.target == "qualification_probe.txt"
         and isinstance(action.payload, dict)
         and action.payload.get("operation") == "replace_text"
         and action.payload.get("old_text") == "OLYMPUS_PROBE_OLD"
         and action.payload.get("new_content") == "OLYMPUS_PROBE_OK"),
        ("repair_after_verifier",
         'VERIFIER ERROR: deliverable quality: provide a semantic main area with one clear primary heading. Existing app/index.html contains exactly <body><div>Rosales Cafe</div></body>. Return only one patch_file action that replaces that exact text with <body><main><h1>Rosales Cafe</h1></main></body> using old_text/new_text.',
         lambda action: action.type == ActionType.PATCH_FILE and action.target == "app/index.html"
         and isinstance(action.payload, dict)
         and action.payload.get("operation") == "replace_text"
         and action.payload.get("old_text") == "<body><div>Rosales Cafe</div></body>"
         and "<main>" in str(action.payload.get("new_content") or "")
         and "<h1>" in str(action.payload.get("new_content") or "")),
    )
    rows = []
    qualified = True
    for name, prompt, validator in probes:
        result = adapter.execute(model, prompt, max_tokens=512, temperature=0.0)
        fabric.observe(route_id, result, provider_hint=provider)
        ok = False
        error = str(result.error or "")
        if result.success and str(result.output or "").strip():
            try:
                ok = bool(validator(normalize_action_text(str(result.output))))
                if not ok:
                    error = "action_protocol_mismatch"
            except Exception as exc:
                error = "action_protocol_invalid: %s" % exc
        fabric.record_probe(provider, route_id, name, ok, latency_ms=result.latency_ms, error=error)
        rows.append({"probe": name, "ok": ok, "error": error or None})
        if not ok:
            qualified = False
            break
    return {"route_id": route_id, "qualified": qualified, "probes": rows}


def run_one(provider: str, model: str) -> dict:
    registry = build_provider_registry(timeout_seconds=90)
    adapter = registry.adapter(provider)
    planner = ModelPlanner(adapter, model)
    with tempfile.TemporaryDirectory(prefix="olympus-provider-proof-") as directory:
        root = Path(directory)
        target = root / "app" / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(INITIAL_HTML, encoding="utf-8")
        initial = AgentState(
            task=TASK,
            selected_model=model,
            max_iterations=6,
            files_modified=("app/index.html",),
            errors=(
                "deliverable quality: semantic main, exact qualification heading, "
                "and data-status=ready are required",
            ),
        )
        verifier = QualificationVerifier(str(root))
        result = AgentLoop(root=str(root), planner=planner, verifier=verifier).run(
            task=TASK,
            selected_model=model,
            max_iterations=6,
            initial_state=initial,
        )
        final_html = target.read_text(encoding="utf-8")
        valid, failures = validate_html(final_html)
        return {
            "provider": provider,
            "model": model,
            "agent_status": result.state.status.value,
            "iterations": result.state.iteration,
            "history": list(result.history),
            "files_modified": list(result.state.files_modified),
            "valid_deliverable": valid,
            "failures": failures,
            "errors": list(result.state.errors)[-5:],
            "passed": result.state.status.value == "completed" and result.state.iteration >= 1 and valid,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=sorted(ALLOWED_PROVIDERS))
    parser.add_argument("--model")
    args = parser.parse_args()

    registry = build_provider_registry(timeout_seconds=90)
    if args.provider not in registry.ids():
        print(json.dumps({"passed": False, "error": "provider_not_configured", "provider": args.provider}))
        return 2
    adapter = registry.adapter(args.provider)
    health = adapter.health()
    if not health.healthy:
        metadata = dict(getattr(health, "metadata", {}) or {})
        safe_metadata = {
            key: value for key, value in metadata.items()
            if key in ("http_status", "kind", "models_count", "error")
        }
        print(json.dumps({
            "passed": False,
            "error": "provider_unhealthy",
            "provider": args.provider,
            "status": health.status,
            "diagnostic": safe_metadata,
        }, ensure_ascii=False, indent=2))
        return 3

    models = choose_models(adapter, args.model)
    if not models:
        print(json.dumps({"passed": False, "error": "no_available_model", "provider": args.provider}))
        return 4

    reports = []
    fabric = CapacityFabric()
    for model in models:
        route_id = provider_route_id(args.provider, model)
        try:
            qualification = qualify_ready_agent(args.provider, model, adapter)
            if not qualification.get("qualified"):
                report = {
                    "provider": args.provider,
                    "model": model,
                    "passed": False,
                    "ready_agent_v2": qualification,
                    "error": "ready_agent_v2_failed",
                }
                reports.append(report)
                fabric.record_live_agent_proof(args.provider, route_id, False, details={"model": model})
                continue
            report = run_one(args.provider, model)
            report["ready_agent_v2"] = qualification
            fabric.record_live_agent_proof(
                args.provider,
                route_id,
                bool(report.get("passed")),
                details={
                    "model": model,
                    "agent_status": report.get("agent_status"),
                    "iterations": report.get("iterations"),
                    "valid_deliverable": report.get("valid_deliverable"),
                },
            )
        except Exception as exc:
            report = {"provider": args.provider, "model": model, "passed": False,
                      "error": "%s: %s" % (type(exc).__name__, exc)}
            fabric.record_live_agent_proof(args.provider, route_id, False, details={"model": model})
        reports.append(report)
        if report.get("passed"):
            print(json.dumps({"provider": args.provider, "passed": True, "proof": report}, ensure_ascii=False, indent=2))
            return 0

    print(json.dumps({"provider": args.provider, "passed": False, "attempts": reports}, ensure_ascii=False, indent=2))
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
