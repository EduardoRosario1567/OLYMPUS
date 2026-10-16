#!/usr/bin/env python3
"""Isolated, fail-closed Docker runner for untrusted Python verification.

Docker must already be available. No shell command interpretation is used.
A successful container run does not by itself attest host/hypervisor security.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

IMAGE = "python:3.11.11-slim-bookworm"


def execute(workspace, module, timeout=40):
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("workspace must be a directory, not a symlink")
    if not module.startswith("tests.") or not all(
        part.isidentifier() for part in module.split(".")
    ):
        raise ValueError("module must be a dotted tests.* identifier")
    if shutil.which("docker") is None:
        raise RuntimeError("BLOCKED: Docker is unavailable; do not execute on host")
    command = [
        "docker", "run", "--rm", "--network", "none",
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "256m", "--cpus", "0.5",
        "--user", "65534:65534", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--mount", "type=bind,src=%s,dst=/work,readonly" % root,
        "--workdir", "/work", "--env", "PYTHONDONTWRITEBYTECODE=1",
        IMAGE, "python", "-m", "unittest", module, "-v",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    return {"status": "DONE" if result.returncode == 0 else "BLOCKED",
            "exit_code": result.returncode,
            "stdout": result.stdout[-6000:], "stderr": result.stderr[-6000:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace")
    parser.add_argument("module")
    args = parser.parse_args()
    try:
        result = execute(args.workspace, args.module)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        result = {"status": "BLOCKED", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "DONE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
