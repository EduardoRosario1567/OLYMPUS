"""Exercise the shipped frontend in Chromium with controlled HTTP responses.

The browser and npm dependencies must already be installed. No test installs
packages, calls providers, or writes into the application runtime.
"""
import functools
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

@functools.lru_cache(maxsize=1)
def browser_results():
    modules = Path(os.environ.get("OLYMPUS_QA_NODE_MODULES", ROOT / "frontend/node_modules")).resolve()
    assert (modules / "playwright").is_dir(), "Existing frontend Playwright dependencies are required"
    with tempfile.TemporaryDirectory(prefix="olympus-ui-") as directory:
        frontend = Path(directory) / "frontend"
        shutil.copytree(ROOT / "frontend", frontend, ignore=shutil.ignore_patterns("node_modules", ".next", ".env*"))
        (frontend / "node_modules").symlink_to(modules, target_is_directory=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        env = dict(os.environ, NEXT_TELEMETRY_DISABLED="1")
        with (Path(directory) / "next.log").open("w+") as log:
            process = subprocess.Popen(["node", str(modules / "next/dist/bin/next"), "dev", "--webpack", "--hostname", "127.0.0.1", "--port", str(port)], cwd=frontend, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                base = "http://127.0.0.1:%s" % port
                deadline = time.monotonic() + 60
                while True:
                    try:
                        with urllib.request.urlopen(base + "/login", timeout=3) as response:
                            assert response.status == 200
                        break
                    except Exception:
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0); raise AssertionError(log.read()[-3000:])
                        time.sleep(.2)
                result = subprocess.run(["node", str(ROOT / "tests/frontend_contract.mjs"), str(modules), base], env=env, text=True, capture_output=True, timeout=120)
                assert result.returncode == 0, result.stderr[-4000:]
                data = json.loads(result.stdout.strip().splitlines()[-1])
                evidence = os.environ.get("OLYMPUS_QA_BROWSER_RESULTS")
                if evidence: Path(evidence).write_text(json.dumps(data, indent=2), encoding="utf-8")
                return data
            finally:
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()

def check_browser(name):
    result = browser_results()["checks"][name]
    assert result is True, result
