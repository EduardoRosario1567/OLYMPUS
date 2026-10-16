#!/usr/bin/env python3
"""Fail-closed readiness check for a *real* Rosales Café agent run.

This deliberately does not call providers, run generated code, or read secrets.
Static checks cannot establish OS-level isolation or inference availability.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def evaluate(root=ROOT, env=None):
    env = os.environ if env is None else env
    issues = []
    acceptance = root / "missions" / "rosales-cafe-acceptance.md"
    if not acceptance.is_file():
        issues.append("MISSION_CONTRACT_MISSING")

    # No trusted sandbox attestation protocol is implemented by this repository.
    # An environment variable, an installed Docker binary, or a temp directory
    # would not constitute proof that the agent actually runs within a sandbox.
    issues.append("OS_SANDBOX_ATTESTATION_UNAVAILABLE")

    # Never infer provider availability from key presence: a working authenticated
    # inference request and its evidence are required separately.
    issues.append("LIVE_PROVIDER_INFERENCE_NOT_VERIFIED")

    return {
        "mission": "rosales-cafe",
        "status": "BLOCKED" if issues else "READY",
        "issues": issues,
        "real_model_calls": 0,
        "generated_site": False,
        "note": "Readiness only; no AI inference or build was attempted",
    }


def main():
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
