#!/usr/bin/env python3
"""Exercise the shipped HTTP ports and one mission through the API.

This deliberately starts real localhost listeners on the same ports used by
the Mac launcher: OmniRoute 20128, backend 8000 and frontend 3000.  The model
transport is deterministic, but the mission crosses the actual HTTP adapter,
FastAPI auth, CloudRuntime, checkpoint, verifier and publication boundaries.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen


PAGE = """<!doctype html><html lang="pt-BR"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Porta Olympus</title><style>:root{color-scheme:dark;--bg:#101827;--panel:#18263a;--line:#31506d;--text:#f8fbff;--muted:#b4c3d4;--accent:#73e0ff}*{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:Arial,sans-serif;background:linear-gradient(135deg,#101827,#16263d);color:var(--text)}main{width:min(720px,calc(100% - 32px));margin:auto;padding:48px 0}nav{display:flex;gap:18px;margin-bottom:28px}nav a{color:var(--accent)}section{padding:24px;margin-top:18px;border:1px solid var(--line);border-radius:18px;background:var(--panel);box-shadow:0 14px 40px #0003}h1{font-size:clamp(2rem,7vw,4rem);line-height:1.04;margin:0 0 16px}h2{margin-top:0}p{color:var(--muted);line-height:1.65}button{border:0;border-radius:12px;padding:14px 20px;background:var(--accent);color:#06111c;font-weight:800;cursor:pointer}button:hover{filter:brightness(1.08)}@media(max-width:640px){main{padding:28px 0}section{padding:18px}nav{gap:12px;flex-wrap:wrap}}</style></head><body><main><nav aria-label="Navegação principal"><a href="#resultado">Resultado</a></nav><h1>Missão executada pela API</h1><p>Entrega produzida através das portas reais do OLYMPUS, com continuidade, validação e publicação do resultado esperado.</p><section><h2>Interação</h2><button id="btn-teste" onclick="this.textContent='Funcionando'">Testar interação</button></section><section><h2>Continuidade</h2><p>Checkpoint e publicação confirmados após a execução do trabalho.</p></section><section id="resultado"><h2>Resultado verificado</h2><p>O artefato foi criado, revisado e disponibilizado para o usuário.</p></section></main></body></html>"""


class ModelHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            self._json(200, {"data": [{"id": "openrouter/openrouter/free", "owned_by": "openrouter"}]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode())
        state = self.server.state  # type: ignore[attr-defined]
        state["calls"] += 1
        state["prompts"].append(json.dumps(request.get("messages", []), ensure_ascii=False))
        action = {
            "type": "create_file",
            "target": "app/index.html",
            "payload": PAGE,
            "reason": "create the requested verified page",
        } if state["calls"] == 1 else {
            "type": "finish",
            "target": None,
            "payload": "verified",
            "reason": "finish after the deliverable is present",
        }
        self._json(200, {"model": request.get("model"), "choices": [{"message": {"content": json.dumps(action, ensure_ascii=False)}}]})


def request_json(url: str, method: str = "GET", payload=None, token: str | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode())


def wait_http(url: str, timeout: float = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("listener did not become ready: " + url)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="olympus-port-e2e-") as directory:
        root = Path(directory)
        model_server = ThreadingHTTPServer(("127.0.0.1", 20128), ModelHandler)
        model_server.state = {"calls": 0, "prompts": []}  # type: ignore[attr-defined]
        model_thread = threading.Thread(target=model_server.serve_forever, daemon=True)
        model_thread.start()

        env = dict(os.environ)
        env.update({
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "OLYMPUS_ADMIN_EMAIL": "admin@olympus.local",
            "OLYMPUS_ADMIN_SENHA": "port-e2e-password",
            "OLYMPUS_JWT_SECRET": "port-e2e-secret-0123456789abcdef-0123456789",
            "OLYMPUS_CLOUD_DATA_DIR": str(root / "cloud"),
            "OLYMPUS_SQLITE_PATH": str(root / "olympus.sqlite3"),
            "OLYMPUS_MEMORY_DB": str(root / "olympus-memory.sqlite3"),
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(root / "provider-settings.json"),
            "OLYMPUS_OMNIROUTE_URL": "http://127.0.0.1:20128",
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "",
            "OLYMPUS_MODEL_TIMEOUT": "5",
        })
        backend = subprocess.Popen(
            ["python3", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(Path(__file__).resolve().parents[1]), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        frontend = subprocess.Popen(
            ["npm", "run", "start", "--", "--hostname", "127.0.0.1", "--port", "3000"],
            cwd=str(Path(__file__).resolve().parents[1] / "frontend"), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            wait_http("http://127.0.0.1:20128/v1/models")
            wait_http("http://127.0.0.1:8000/health")
            wait_http("http://127.0.0.1:3000")
            _, login = request_json("http://127.0.0.1:8000/auth/login", "POST", {"email": "admin@olympus.local", "senha": "port-e2e-password"})
            token = login["access_token"]
            _, project = request_json("http://127.0.0.1:8000/cloud/projects", "POST", {"project_id": "port-e2e", "name": "Port E2E"}, token)
            request_json(
                "http://127.0.0.1:8000/memory", "POST",
                {"type": "preference", "key": "continuidade missão", "value": {"note": "continue through the verified HTTP mission"}, "project_id": project["project_id"]}, token,
            )
            _, stored_memory = request_json(
                "http://127.0.0.1:8000/memory", token=token,
            )
            _, execution = request_json(
                "http://127.0.0.1:8000/cloud/missions", "POST",
                {"project_id": project["project_id"], "task": "Execute a missão com continuidade e publique uma página web completa e responsiva com botão", "max_iterations": 24}, token,
            )
            execution_id = execution["execution_id"]
            deadline = time.time() + 15
            while time.time() < deadline:
                _, current = request_json("http://127.0.0.1:8000/cloud/executions/" + execution_id, token=token)
                if current["status"] in {"completed", "failed", "blocked"}:
                    break
                time.sleep(0.2)
            _, events = request_json("http://127.0.0.1:8000/cloud/executions/" + execution_id + "/events", token=token)
            checks = {
                "omniroute_port_20128": model_server.state["calls"] >= 1,  # type: ignore[attr-defined]
                "backend_port_8000": True,
                "frontend_port_3000": True,
                "authenticated_http_flow": bool(token),
                "mission_completed": current["status"] == "completed",
                "verification_event": any(item["event"] == "verification_started" for item in events["events"]),
                "publication_event": any(item["event"] == "result_published" for item in events["events"]),
                "memory_persisted": any(item["key"] == "continuidade missão" for item in stored_memory["memories"]),
                "memory_context_loaded": any(item["event"] == "memory_context_loaded" for item in events["events"]),
                "memory_in_prompt": any("CONTEXTO CONFIRMADO" in prompt for prompt in model_server.state["prompts"]),  # type: ignore[attr-defined]
                "memory_context_saved": any(item["event"] == "memory_context_saved" for item in events["events"]),
            }
            result = {"status": "PASS" if all(checks.values()) else "FAIL", "status_detail": current["status"], "error": current.get("error"), "model_calls": model_server.state["calls"], "checks": checks, "events": events["events"]}  # type: ignore[attr-defined]
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "PASS" else 1
        finally:
            for process in (frontend, backend):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            model_server.shutdown()
            model_server.server_close()
            model_thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
