#!/usr/bin/env python3
"""Static contract gate for the macOS command-line package.

The Work runtime cannot boot the macOS kernel, but it can validate the safety
contract of the shipped .command files before a package reaches a user.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ("INSTALAR-OLYMPUS.command", "start_olympus.command", "stop_olympus.command", "configure_ai.command")


def main() -> int:
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    for name in COMMANDS:
        path = ROOT / name
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        checks["syntax:%s" % name] = result.returncode == 0
        details["syntax:%s" % name] = result.stderr.strip()

    installer = (ROOT / "INSTALAR-OLYMPUS.command").read_text(encoding="utf-8")
    starter = (ROOT / "start_olympus.command").read_text(encoding="utf-8")
    stopper = (ROOT / "stop_olympus.command").read_text(encoding="utf-8")

    checks.update({
        "installer:macos_guard": 'uname -s' in installer and 'Darwin' in installer,
        "installer:version_from_manifest": "frontend/public/olympus-version.json" in installer,
        "installer:private_target": 'Documents/OLYMPUS-PILOTO' in installer,
        "starter:loopback_backend": "127.0.0.1 --port 8000" in starter,
        "starter:loopback_frontend": "--hostname 127.0.0.1" in starter,
        "starter:version_healthcheck": "backend_current" in starter and "frontend_current" in starter,
        "starter:owned_process_checks": "listener_cwd" in starter and "lsof" in starter,
        "starter:omniroute_probe": "127.0.0.1:20128/v1/models" in starter,
        "stopper:pid_files_only": "RUNTIME_DIR" in stopper and "kill \"$pid\"" in stopper,
        "stopper:no_broad_killall": "killall" not in stopper and "pkill" not in stopper,
        "no_embedded_api_keys": not bool(re.search(r"(?:sk-|AIza|xai-)[A-Za-z0-9_-]{16,}", installer + starter + stopper)),
    })

    status = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "product": "OLYMPUS",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "details": details,
    }
    target = ROOT / ".olympus" / "qa" / "macos-command-gate.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
