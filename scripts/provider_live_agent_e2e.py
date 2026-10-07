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
from olympus.agent.loop import AgentLoop
from olympus.agent.planner import ModelPlanner
from olympus.agent.state import AgentState
from olympus.agent.verifier import AgentVerifier


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
        print(json.dumps({"passed": False, "error": "provider_unhealthy", "provider": args.provider,
                          "status": health.status}, ensure_ascii=False))
        return 3

    models = choose_models(adapter, args.model)
    if not models:
        print(json.dumps({"passed": False, "error": "no_available_model", "provider": args.provider}))
        return 4

    reports = []
    for model in models:
        try:
            report = run_one(args.provider, model)
        except Exception as exc:
            report = {"provider": args.provider, "model": model, "passed": False,
                      "error": "%s: %s" % (type(exc).__name__, exc)}
        reports.append(report)
        if report.get("passed"):
            print(json.dumps({"provider": args.provider, "passed": True, "proof": report}, ensure_ascii=False, indent=2))
            return 0

    print(json.dumps({"provider": args.provider, "passed": False, "attempts": reports}, ensure_ascii=False, indent=2))
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
