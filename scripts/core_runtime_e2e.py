#!/usr/bin/env python3
"""Deterministic end-to-end gate for the OLYMPUS core runtime.

This test uses a local OpenAI-compatible HTTP server, so it exercises the same
transport used by OmniRouteAdapter without depending on external quotas or
credentials.  The primary route creates an intentionally incomplete page and
then fails with HTTP 429.  The control plane must hand the checkpoint to the
fallback route, repair the page, verify it and close the mission.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.runtime import CloudRuntime
from olympus.routing.omniroute_adapter import OmniRouteAdapter


COMPLETE_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Olympus — missão concluída</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #0b1220; color: #f7fbff; }
    main { width: min(960px, calc(100% - 32px)); margin: 0 auto; padding: 64px 0; }
    nav { display: flex; gap: 16px; margin-bottom: 56px; }
    nav a { color: #75ddff; }
    h1 { max-width: 720px; font-size: clamp(2.3rem, 7vw, 5rem); line-height: 1.02; }
    p { max-width: 640px; color: #b7c6d8; line-height: 1.7; }
    section { margin-top: 32px; padding: 24px; border: 1px solid #28405d; border-radius: 18px; }
    @media (max-width: 640px) { main { padding: 32px 0; } nav { flex-wrap: wrap; } }
  </style>
</head>
<body>
  <main>
    <nav aria-label="Navegação principal"><a href="#inicio">Início</a><a href="#processo">Processo</a></nav>
    <section id="inicio"><p>OLYMPUS · RESULTADO VERIFICADO</p><h1>Da intenção à entrega, com continuidade.</h1><p>Esta página comprova que o núcleo recebeu uma missão, executou uma alteração, superou uma falha de rota e validou o resultado final.</p></section>
    <section id="processo"><h2>Missão concluída</h2><p>Planejamento, execução, fallback automático, verificação e persistência foram atravessados em uma única cadeia operacional.</p></section>
    <section id="continuidade"><h2>Resultado preservado</h2><p>O checkpoint mantém a alteração e identifica as rotas utilizadas, permitindo retomar com segurança quando um provedor falha.</p></section>
  </main>
</body>
</html>
"""


class Selector:
    def select_candidates(self, _task: str):
        return ("primary/free", "fallback/free")


class ProviderHandler(BaseHTTPRequestHandler):
    server_version = "OlympusE2E/1.0"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": "primary/free", "owned_by": "primary"},
                {"id": "fallback/free", "owned_by": "fallback"},
            ]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        model = payload.get("model", "")
        state = self.server.state  # type: ignore[attr-defined]
        state["calls"].append(model)

        if model == "primary/free":
            if state["primary_calls"] == 0:
                state["primary_calls"] += 1
                content = json.dumps({
                    "type": "create_file",
                    "target": "app/index.html",
                    "payload": "<html><body><h1>Welcome</h1></body></html>",
                    "reason": "initial draft",
                })
                self._success(model, content)
                return
            state["primary_calls"] += 1
            self._json(429, {"error": {
                "message": "rate limit reached",
                "type": "rate_limit",
                "code": "rate_limit",
            }})
            return

        if model == "fallback/free":
            if state["fallback_calls"] == 0:
                state["fallback_calls"] += 1
                self._success(model, json.dumps({'type': 'create_file', 'target': 'docs/delivery-concept.md', 'payload': '# Visual thesis\nA clear brand composition with restrained color, deliberate typography and readable spacing.\n# Content plan\nBrand, offer, detail and primary action.\n# Interaction plan\nNavigation and controls follow the requested workflow.\n# Evidence\nSynthetic fixture only. No claims about a real business. Browser and visual review pending.\n', 'reason': 'define the delivery concept'}))
                return
            if state["fallback_calls"] == 1:
                state["fallback_calls"] += 1
                content = json.dumps({
                    "type": "patch_file",
                    "target": "app/index.html",
                    "payload": {
                        "operation": "replace_lines",
                        "start_line": 1,
                        "end_line": 1,
                        "new_content": COMPLETE_HTML,
                    },
                    "reason": "repair the incomplete draft",
                })
                self._success(model, content)
                return
            state["fallback_calls"] += 1
            self._success(model, json.dumps({
                "type": "finish",
                "target": None,
                "payload": "verified",
                "reason": "all acceptance checks pass",
            }))
            return

        self._json(400, {"error": {"message": "unknown model"}})

    def _success(self, model: str, content: str) -> None:
        self._json(200, {
            "id": "e2e-response",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        })

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def run() -> dict[str, Any]:
    root_parent = tempfile.TemporaryDirectory(prefix="olympus-core-e2e-")
    root = Path(root_parent.name)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
    server.state = {"calls": [], "primary_calls": 0, "fallback_calls": 0}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        task = (
            "Crie uma página web responsiva e completa para demonstrar o fluxo do OLYMPUS, "
            "com navegação, conteúdo significativo, acessibilidade, estilo próprio e validação "
            "antes de concluir."
        )
        router = OmniRouteAdapter(
            base_url="http://127.0.0.1:%d" % server.server_port,
            timeout_seconds=2,
        )
        runtime = CloudRuntime(
            str(root / "cloud"),
            lambda workspace, telemetry: AutonomousDeveloper(
                workspace, router, selector=Selector(), telemetry=telemetry,
            ),
            max_workers=1,
        )
        try:
            submitted = runtime.submit("core-e2e", task, max_iterations=12, project_name="Core E2E")
            deadline = time.time() + 5
            record = submitted
            while record.status not in {"completed", "failed", "blocked"} and time.time() < deadline:
                time.sleep(0.02)
                record = runtime.get(submitted.execution_id)
            if record is None:
                raise RuntimeError("execution record disappeared")
            result = record
            project_root = runtime.projects.project_root("core-e2e")
            checkpoint_path = Path(submitted.workspace) / ".olympus" / "checkpoints" / "DEVELOP.json"
            output = project_root / "app" / "index.html"
            archive = runtime.projects.export_zip("core-e2e")
            previews = ProjectPreviewSessions(runtime.projects)
            preview = previews.create("core-e2e")
            _, preview_file = previews.resolve(preview.token)
            runtime_events = runtime.events(submitted.execution_id)
            versions = runtime.versions.list("core-e2e")
        finally:
            runtime.close()
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        checks = {
            "mission_completed": result.status == "completed",
            "http_models_probe": router.health().healthy,
            "primary_attempted": server.state["primary_calls"] >= 2,
            "fallback_attempted": server.state["fallback_calls"] >= 2,
            "cross_provider_failover": any(
                event.get("event") == "model_failover" and event.get("cross_provider")
                for event in runtime_events
            ),
            "checkpoint_handoff": any(
                event.get("event") == "model_resume"
                and "app/index.html" in event.get("files_modified", [])
                for event in runtime_events
            ),
            "verified_output": output.is_file() and "RESULTADO VERIFICADO" in output.read_text(encoding="utf-8"),
            "checkpoint_completed": checkpoint.get("status") == "completed",
            "checkpoint_has_models": checkpoint.get("models_attempted") == ["primary/free", "fallback/free"],
            "published_to_project": output.is_file(),
            "previewable": preview.entrypoint == "app/index.html" and preview_file.is_file(),
            "downloadable": archive.is_file() and archive.stat().st_size > 0,
            "versioned": len(versions) == 2,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise RuntimeError("core E2E failed: %s; result=%s; error=%s; events=%s; checkpoint=%s" % (
                ", ".join(failed), result.status, getattr(result, "error", None),
                json.dumps(runtime_events, ensure_ascii=False), json.dumps(checkpoint, ensure_ascii=False),
            ))
        return {
            "status": "PASS",
            "mission_status": result.status,
            "models_attempted": checkpoint.get("models_attempted", []),
            "http_calls": list(server.state["calls"]),
            "checks": checks,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        root_parent.cleanup()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
