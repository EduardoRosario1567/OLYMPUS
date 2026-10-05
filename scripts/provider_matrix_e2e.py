#!/usr/bin/env python3
"""Integrated provider-matrix gate for the OLYMPUS core.

The matrix uses the real provider adapters and the real asynchronous CloudRuntime
against a local HTTP server implementing the wire protocols currently supported
by the product.  It deliberately exercises many independent free routes in one
large multi-step mission, while injecting transport, token-budget and protocol
failures that the runtime must recover from.
"""

from __future__ import annotations

import json
from dataclasses import replace
import os
import re
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

from backend.app.core.provider_runtime import build_provider_registry
from olympus.agent.mission import AutonomousPatchRunner, parse_mission
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.runtime import CloudRuntime
from olympus.routing.provider_fabric import MultiProviderRoutingAdapter


PROVIDER_MODELS = {
    "omniroute": "omni/free-stage",
    "fcc": "nvidia_nim/stage-free",
    "openrouter": "openrouter/free-stage",
    "groq": "groq/free-stage",
    "cerebras": "cerebras/free-stage",
    "ollama": "ollama/stage-free",
    "gemini": "gemini-2.5-flash",
    "mistral": "mistral-small-latest",
    "zai": "glm-4.7-flash",
    "cloudflare": "@cf/qwen/stage-free",
}


def _file_payload(provider: str, target: str) -> str:
    if target == "app/index.html":
        payload: Any = """<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Olympus Matrix</title><link rel="stylesheet" href="styles.css"></head>
<body><main><nav aria-label="Navegação principal"><a href="#inicio">Início</a><a href="#dados">Dados</a><a href="#entrega">Entrega</a></nav><section id="inicio"><p>OLYMPUS · PROJETO INTEGRADO</p><h1>Uma missão grande atravessada por várias inteligências.</h1><p>O núcleo coordena fontes independentes, preserva o progresso e entrega uma aplicação verificável.</p></section><section id="dados"><h2>Dados preservados</h2><p>Rotas, decisões e artefatos permanecem rastreáveis.</p></section><section id="entrega"><h2>Entrega concluída</h2><p>O projeto foi construído, testado, versionado e preparado para publicação.</p></section></main><script src="app.js"></script></body>
</html>"""
    elif target == "app/styles.css":
        payload = "body{font-family:system-ui,sans-serif;background:#0b1220;color:#f7fbff}main{max-width:960px;margin:auto;padding:48px 24px}nav{display:flex;gap:18px}a{color:#75ddff}section{margin-top:32px;padding:24px;border:1px solid #28405d;border-radius:18px}@media(max-width:640px){main{padding:28px 16px}}"
    elif target == "app/app.js":
        payload = "document.documentElement.dataset.olympusRoute = %r;" % provider
    elif target == "data/project.json":
        payload = json.dumps({"project": "OLYMPUS", "mode": "integrated", "route": provider, "verified": True})
    elif target == "backend/health.py":
        payload = "def health():\n    return {'service': 'olympus', 'status': 'ok', 'route': %r}\n" % provider
    elif target == "tests/test_deliverable.py":
        payload = "from pathlib import Path\n\ndef test_linked_assets_exist():\n    root = Path(__file__).resolve().parents[1]\n    html = (root / 'app/index.html').read_text()\n    for name in ('styles.css', 'app.js'):\n        assert name in html\n        assert (root / 'app' / name).is_file()\n"
    elif target == "docs/ARCHITECTURE.md":
        payload = "# Arquitetura integrada\n\nO núcleo coordena roteamento, checkpoint, verificação e publicação.\n"
    elif target == "README.md":
        payload = "# Projeto OLYMPUS\n\nArtefato criado por missão multi-provider.\n"
    elif target == "config/runtime.json":
        payload = json.dumps({"runtime": "cloud", "failover": "checkpoint", "provider": provider})
    else:
        payload = "OLYMPUS artifact from %s\n" % provider
    return json.dumps({
        "type": "create_file",
        "target": target,
        "payload": payload,
        "reason": "matrix stage delivery",
    }, ensure_ascii=False)


STAGES = (
    ("omniroute", "app/index.html"),
    ("fcc", "app/styles.css"),
    ("openrouter", "app/app.js"),
    ("groq", "data/project.json"),
    ("cerebras", "backend/health.py"),
    ("ollama", "tests/test_deliverable.py"),
    ("gemini", "docs/ARCHITECTURE.md"),
    ("mistral", "README.md"),
    ("zai", "config/runtime.json"),
    ("cloudflare", "manifest.txt"),
)


class MatrixSelector:
    def select_candidates(self, task: str):
        match = re.search(r"MATRIX_PROVIDER=([a-z0-9_-]+)", task)
        if not match:
            raise RuntimeError("matrix provider marker missing")
        provider = match.group(1)
        model = PROVIDER_MODELS[provider]
        route = "%s::%s" % (provider, model)
        if provider == "omniroute":
            return (route, "fcc::%s" % PROVIDER_MODELS["fcc"])
        return (route,)


class MatrixHandler(BaseHTTPRequestHandler):
    server_version = "OlympusProviderMatrix/1.0"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _provider(self) -> str:
        path = self.path.strip("/").split("/")
        return path[0] if path else "unknown"

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
        provider = self._provider()
        if provider not in PROVIDER_MODELS:
            self._json(404, {"error": {"message": "unknown provider"}})
            return
        model = PROVIDER_MODELS[provider]
        self.server.state["health_calls"].append(provider)  # type: ignore[attr-defined]
        if provider == "gemini":
            self._json(200, {"models": [{"name": "models/" + model, "supportedGenerationMethods": ["generateContent"], "inputTokenLimit": 32768, "outputTokenLimit": 8192}]})
        else:
            self._json(200, {"object": "list", "data": [{"id": model, "owned_by": provider}]})

    def do_POST(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
        provider = self._provider()
        if provider not in PROVIDER_MODELS:
            self._json(404, {"error": {"message": "unknown provider"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        model = str(body.get("model") or PROVIDER_MODELS[provider])
        prompt = str(body.get("input") or body.get("messages", [{}])[-1].get("content") or "")
        if provider == "gemini":
            prompt = "\n".join(part.get("text", "") for item in body.get("contents", []) for part in item.get("parts", []))
        stage = re.search(r"MATRIX_PROVIDER=([a-z0-9_-]+)", prompt)
        stage_key = stage.group(1) if stage else provider
        key = "%s:%s" % (provider, stage_key)
        state = self.server.state  # type: ignore[attr-defined]
        state["calls"].append({"provider": provider, "model": model, "stage": stage_key, "path": self.path})
        count = state["stage_calls"].get(key, 0)
        state["stage_calls"][key] = count + 1

        if provider == "omniroute" and stage_key == "omniroute" and count == 0:
            self._json(429, {"error": {"message": "rate limit reached", "type": "rate_limit", "code": "rate_limit"}})
            return

        if provider == "groq" and count == 0:
            self._json(400, {"error": {"message": "max_tokens must be less than or equal to 1024", "type": "invalid_request_error"}})
            return

        if provider == "zai" and count == 0:
            failed = _file_payload(provider, "config/runtime.json")
            self._json(400, {"error": {"message": "tool_use_failed", "failed_generation": failed}})
            return

        target = dict(STAGES)[stage_key]
        # The first Groq/Z.AI response is a recoverable protocol error.  The
        # next response must still deliver the stage action; only the response
        # after that is the explicit finish action.
        delivery_count = count - 1 if provider in {"groq", "zai"} else count
        if delivery_count == 0:
            content = _file_payload(provider, target)
        else:
            content = json.dumps({"type": "finish", "target": None, "payload": "verified", "reason": "stage acceptance checks pass"})

        if provider == "gemini":
            self._json(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": content}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10}})
        elif provider == "fcc":
            self._json(200, {"id": "matrix-response", "model": model, "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}], "usage": {"input_tokens": 10, "output_tokens": 10}})
        else:
            self._json(200, {"id": "matrix-chat", "model": model, "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 10}})

    def log_message(self, _format: str, *_args: Any) -> None:
        return


class MatrixDeveloper:
    def __init__(self, root: str, router: MultiProviderRoutingAdapter, telemetry):
        self.runner = AutonomousPatchRunner(root, router, selector=MatrixSelector(), telemetry=telemetry)

    def run(self, task: str, max_iterations: int = 12, resume: bool = True):
        return self.runner.run(parse_mission(task), resume=resume)


def _mission_text() -> str:
    lines = ["# OLYMPUS Provider Matrix"]
    for index, (provider, target) in enumerate(STAGES, 1):
        lines.extend((
            "## STEP %02d — %s" % (index, provider),
            "MATRIX_PROVIDER=%s Entregue a etapa do grande projeto OLYMPUS criando o artefato %s, preservando o trabalho anterior e verificando antes de concluir." % (provider, target),
            "",
        ))
    return "\n".join(lines)


def run() -> dict[str, Any]:
    temp = tempfile.TemporaryDirectory(prefix="olympus-provider-matrix-")
    root = Path(temp.name)
    server = ThreadingHTTPServer(("127.0.0.1", 0), MatrixHandler)
    server.state = {"calls": [], "health_calls": [], "stage_calls": {}}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_port
    env = {
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
        "OLYMPUS_OMNIROUTE_URL": base + "/omniroute",
        "OLYMPUS_FCC_URL": base + "/fcc",
        "OLYMPUS_OPENROUTER_URL": base + "/openrouter",
        "OLYMPUS_GROQ_URL": base + "/groq",
        "OLYMPUS_CEREBRAS_URL": base + "/cerebras",
        "OLYMPUS_OLLAMA_URL": base + "/ollama",
        "OLYMPUS_GEMINI_URL": base + "/gemini",
        "OLYMPUS_MISTRAL_URL": base + "/mistral",
        "OLYMPUS_ZAI_URL": base + "/zai",
        "OLYMPUS_CLOUDFLARE_URL": base + "/cloudflare",
        "CLOUDFLARE_ACCOUNT_ID": "synthetic-matrix-account",
        "FCC_PROXY_TOKEN": "matrix-token",
        "GROQ_API_KEY": "matrix-key",
        "OPENROUTER_API_KEY": "matrix-key",
        "CEREBRAS_API_KEY": "matrix-key",
        "GEMINI_API_KEY": "matrix-key",
        "MISTRAL_API_KEY": "matrix-key",
        "ZAI_API_KEY": "matrix-key",
        "CLOUDFLARE_API_KEY": "matrix-key",
        "OLYMPUS_FREE_FALLBACK_PROVIDERS": ",".join(PROVIDER_MODELS.keys()),
        "OLYMPUS_PROVIDER_SETTINGS_PATH": str(root / "provider-settings.json"),
    }
    try:
        with patch.dict(os.environ, env, clear=True):
            registry = build_provider_registry(timeout_seconds=2)
            # Cloudflare catalog uses a separate account-scoped URL. Route only
            # that fixture boundary to our local native catalog server.
            cloudflare = registry.adapter("cloudflare")
            cloudflare.config = replace(cloudflare.config, catalog_url=base + "/cloudflare/models")
            expected = set(PROVIDER_MODELS)
            active_health = {row.provider for row in registry.health_all() if row.healthy}
            catalog_sources = {
                provider for provider in expected
                if registry.adapter(provider).list_models()
            }
            router = MultiProviderRoutingAdapter(registry, default_provider="omniroute")
            events: list[dict[str, Any]] = []
            runtime = CloudRuntime(
                str(root / "cloud"),
                lambda workspace, telemetry: MatrixDeveloper(workspace, router, telemetry),
                max_workers=1,
            )
            try:
                submitted = runtime.submit("provider-matrix", _mission_text(), max_iterations=80, project_name="Provider Matrix")
                record = submitted
                deadline = time.time() + 15
                while record.status not in {"completed", "failed", "blocked"} and time.time() < deadline:
                    time.sleep(0.03)
                    record = runtime.get(submitted.execution_id)
                events = runtime.events(submitted.execution_id)
                project_root = runtime.projects.project_root("provider-matrix")
                archive = runtime.projects.export_zip("provider-matrix")
                if record.status != "completed":
                    raise RuntimeError("provider matrix mission ended as %s: %s; calls=%s; events=%s" % (
                        record.status, record.error,
                        json.dumps(server.state["calls"], ensure_ascii=False),
                        json.dumps(events, ensure_ascii=False),
                    ))
                previews = ProjectPreviewSessions(runtime.projects)
                preview = previews.create("provider-matrix")
                _, preview_file = previews.resolve(preview.token)
                versions = runtime.versions.list("provider-matrix")
            finally:
                runtime.close()
            checks = {
                "all_registered_free_sources_healthy": expected.issubset(active_health),
                "all_free_sources_cataloged": expected.issubset(catalog_sources),
                "large_mission_completed": record.status == "completed",
                "all_stages_attempted": expected.issubset({item["stage"] for item in server.state["calls"]}),
                "omniroute_failover": any(item.get("event") == "model_failover" and item.get("from_provider") == "omniroute" and item.get("to_provider") == "fcc" for item in events),
                "checkpoint_continuity": any(item.get("event") == "model_resume" for item in events),
                "groq_token_repair": any(item["provider"] == "groq" for item in server.state["calls"]) and server.state["stage_calls"].get("groq:groq", 0) >= 2,
                "zai_protocol_recovery": any(item["provider"] == "zai" for item in server.state["calls"]) and server.state["stage_calls"].get("zai:zai", 0) >= 2,
                "all_artifacts_present": all((project_root / target).is_file() for _, target in STAGES),
                "published_and_versioned": len(versions) == 2,
                "previewable": preview.entrypoint == "app/index.html" and preview_file.is_file(),
                "downloadable": archive.is_file() and archive.stat().st_size > 0,
            }
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                raise RuntimeError("provider matrix failed: %s; status=%s; calls=%s; events=%s" % (
                    ", ".join(failed), record.status, json.dumps(server.state["calls"], ensure_ascii=False), json.dumps(events, ensure_ascii=False),
                ))
            return {
                "status": "PASS",
                "mission_status": record.status,
                "registered_sources": sorted(expected),
                "calls_by_provider": {provider: sum(1 for item in server.state["calls"] if item["provider"] == provider) for provider in sorted(expected)},
                "checks": checks,
            }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temp.cleanup()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
