#!/usr/bin/env python3
"""Release gate for OLYMPUS.

This gate is deliberately independent of real provider quotas.  It validates
the contract that must remain true even when a provider returns 429, malformed
output, a timeout, or disappears during a mission:

* complete regression suite;
* cross-provider failover and checkpoint handoff;
* large multi-provider mission;
* publication, preview, versioning and downloadable artifact.

The command exits non-zero on any failed gate and writes a machine-readable
report to .olympus/qa/release-gate.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".olympus" / "qa" / "release-gate.json"


def run_gate(name: str, command: list[str]) -> dict:
    started = time.monotonic()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "backend")))
    process = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = process.stdout[-12000:]
    blocked = process.returncode != 0 and '"status": "BLOCKED"' in output
    return {
        "name": name,
        "status": "PASS" if process.returncode == 0 else "BLOCKED" if blocked else "FAIL",
        "exit_code": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "output": output,
    }


def main() -> int:
    gates = [
        ("actual-container-isolation", [sys.executable, "scripts/container_isolation_gate.py"]),
        ("actual-preview-isolation-frameworks", [sys.executable, "scripts/preview_isolation_gate.py"]),
        (
            "unit-and-contract-regression",
            [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
        ),
        ("core-failover-checkpoint-e2e", [sys.executable, "scripts/core_runtime_e2e.py"]),
        ("provider-matrix-mission-e2e", [sys.executable, "scripts/provider_matrix_e2e.py"]),
        ("macos-command-contract", [sys.executable, "scripts/macos_command_gate.py"]),
        ("blind-mission-dom-interaction", [sys.executable, "scripts/blind_mission_gate.py"]),
    ]

    results = []
    for name, command in gates:
        result = run_gate(name, command)
        results.append(result)
        print("[%s] %s (%ss)" % (result["status"], name, result["duration_seconds"]))
        if result["status"] in {"FAIL", "BLOCKED"}:
            print(result["output"])
            break

    report = {
        "product": "OLYMPUS",
        "gate_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if results and all(item["status"] == "PASS" for item in results) and len(results) == len(gates) else "BLOCKED" if any(item["status"] == "BLOCKED" for item in results) else "FAIL",
        "root": str(ROOT),
        "gates": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Relatório: %s" % REPORT)
    print("RELEASE GATE: %s" % report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
