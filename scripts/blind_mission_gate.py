#!/usr/bin/env python3
"""Independent mission gate with browser-level interaction validation."""

from __future__ import annotations

import json
import os
import glob
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.runtime import CloudRuntime
from olympus.routing.provider_fabric import MultiProviderRoutingAdapter, OpenAICompatibleAdapter, ProviderConfig, ProviderRegistry
from olympus.routing.omniroute_adapter import OmniRouteAdapter


FINAL_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OLYMPUS — Entrega verificada</title>
<style>body{margin:0;background:#0b1220;color:#f7fbff;font-family:system-ui,sans-serif}main{width:min(760px,calc(100% - 32px));margin:0 auto;padding:64px 0}nav{display:flex;gap:18px;margin-bottom:28px}nav a{color:#73e0ff}section{padding:28px;margin-top:20px;border:1px solid #304866;border-radius:20px;background:#111d31}h1{font-size:clamp(2rem,7vw,4rem);line-height:1.05}p{color:#b9c7d8;line-height:1.65}button{border:0;border-radius:12px;padding:14px 20px;background:#73e0ff;color:#06111c;font-weight:800;cursor:pointer}@media(max-width:640px){main{padding:32px 0}}</style>
</head><body><main><nav aria-label="Navegação principal"><a href="#inicio">Início</a><a href="#processo">Processo</a><a href="#entrega">Entrega</a></nav><section id="inicio"><p>OLYMPUS · RESULTADO VERIFICADO</p><h1>Missão concluída com continuidade.</h1><p>Esta entrega foi criada, reparada, validada e publicada após uma troca de provedor. O artefato permanece disponível mesmo quando a primeira rota falha.</p></section><section id="processo"><h2>Processo preservado</h2><p>O checkpoint manteve o trabalho produzido e permitiu continuar a missão em uma rota gratuita independente.</p></section><section id="entrega"><h2>Interação validada</h2><button id="btn-teste" type="button" onclick="this.textContent='Botão funcionando';document.getElementById('status').textContent='Interação validada'">Testar interação</button><p id="status" aria-live="polite">Aguardando interação</p></section></main></body></html>"""


class BrowserUnavailable(RuntimeError):
    pass


class Selector:
    def select_candidates(self, _task: str):
        return ("blind-primary::blind/primary", "blind-fallback::blind/fallback")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode())
        model = str(request.get("model", ""))
        state = self.server.state  # type: ignore[attr-defined]
        state["calls"].append(model)
        if model == "blind/primary":
            self._json(429, {"error": {"message": "free-models-per-day", "code": "rate_limit"}})
            return
        if model == "blind/fallback":
            if state["fallback_calls"] == 0:
                state["fallback_calls"] += 1
                content = json.dumps({"type": "create_file", "target": "app/index.html", "payload": FINAL_HTML, "reason": "deliver verified interactive page"}, ensure_ascii=False)
            else:
                state["fallback_calls"] += 1
                content = json.dumps({"type": "finish", "target": None, "payload": "verified", "reason": "browser contract passed"})
            self._json(200, {"id": "blind", "choices": [{"message": {"role": "assistant", "content": content}}]})
            return
        self._json(400, {"error": {"message": "unknown model"}})

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": "blind/primary"}, {"id": "blind/fallback"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def log_message(self, *_args):
        return


def browser_click(path: Path) -> dict[str, Any]:
    script = r'''
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.argv[2]});
  const page = await browser.newPage();
  await page.goto('file://' + process.argv[1]);
  await page.locator('#btn-teste').click();
  const button = await page.locator('#btn-teste').textContent();
  const status = await page.locator('#status').textContent();
  await browser.close();
  if (button !== 'Botão funcionando' || status !== 'Interação validada') process.exit(2);
  console.log(JSON.stringify({button, status}));
})().catch(error => { console.error(error.stack || error); process.exit(1); });
'''
    browser_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    cache_root = Path(browser_cache) if browser_cache and browser_cache != "0" else Path.home() / ".cache" / "ms-playwright"
    candidates = glob.glob(str(cache_root / "chromium-*/chrome-linux64/chrome"))
    candidates.extend(glob.glob(str(cache_root / "chromium_headless_shell-*/chrome-linux64/chrome")))
    root = Path(__file__).resolve().parents[1]
    node_env = dict(os.environ)
    module_root = root / "frontend" / "node_modules"
    if module_root.is_dir():
        node_env["NODE_PATH"] = str(module_root) + os.pathsep + node_env.get("NODE_PATH", "")
    if not candidates:
        dom_script = r'''
const fs = require('fs');
const { JSDOM } = require('jsdom');
const source = fs.readFileSync(process.argv[1], 'utf8');
const dom = new JSDOM(source, { runScripts: 'dangerously', resources: 'usable', url: 'file://' + process.argv[1] });
const button = dom.window.document.querySelector('#btn-teste');
if (!button) throw new Error('DOM runtime: button not found');
button.click();
const result = button.textContent;
const status = dom.window.document.querySelector('#status')?.textContent || '';
if (result !== 'Botão funcionando' || status !== 'Interação validada') process.exit(2);
console.log(JSON.stringify({result, status, validator: 'jsdom-runtime'}));
'''
        dom_result = subprocess.run(
            ["node", "-e", dom_script, str(path)],
            capture_output=True,
            text=True,
            env=node_env,
        )
        if dom_result.returncode == 0:
            return json.loads(dom_result.stdout.strip())
        if "Cannot find module 'jsdom'" not in (dom_result.stderr or ""):
            raise RuntimeError("DOM runtime interaction failed: %s" % (dom_result.stderr or dom_result.stdout))
        raise BrowserUnavailable(
            "browser validation is unavailable: install Playwright Chromium or jsdom before running this gate"
        )
    result = subprocess.run(
        ["node", "-e", script, str(path), candidates[0]],
        capture_output=True,
        text=True,
        env=node_env,
    )
    if result.returncode != 0:
        raise RuntimeError("browser interaction failed: %s" % (result.stderr or result.stdout))
    return json.loads(result.stdout.strip())


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="olympus-blind-") as temp:
        root = Path(temp)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.state = {"calls": [], "fallback_calls": 0}  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        runtime = None
        try:
            base = "http://127.0.0.1:%d/v1" % server.server_port
            registry = ProviderRegistry()
            registry.register("blind-primary", OpenAICompatibleAdapter(ProviderConfig("blind-primary", base, timeout_seconds=2)), 10)
            registry.register("blind-fallback", OpenAICompatibleAdapter(ProviderConfig("blind-fallback", base, timeout_seconds=2)), 20)
            router = MultiProviderRoutingAdapter(registry, default_provider="blind-primary")
            runtime = CloudRuntime(str(root / "cloud"), lambda workspace, telemetry: AutonomousDeveloper(workspace, router, selector=Selector(), telemetry=telemetry), max_workers=1)
            task = "Crie uma página web responsiva completa com um botão id btn-teste que ao clicar deve exibir Botão funcionando. Publique, abra o preview e valide a interação antes de concluir."
            execution = runtime.submit("blind-mission", task, max_iterations=8, project_name="Blind Mission")
            record = execution
            deadline = time.time() + 8
            while record.status not in {"completed", "failed", "blocked"} and time.time() < deadline:
                time.sleep(0.03)
                record = runtime.get(execution.execution_id)
            if record.status != "completed":
                raise RuntimeError("blind mission ended as %s: %s; calls=%s; summary=%s; events=%s" % (record.status, record.error, server.state["calls"], record.result_summary, runtime.events(execution.execution_id)))
            root_file = runtime.projects.project_root("blind-mission") / "app" / "index.html"
            previews = ProjectPreviewSessions(runtime.projects)
            preview = previews.create("blind-mission")
            _, preview_file = previews.resolve(preview.token)
            try:
                browser = browser_click(preview_file)
            except BrowserUnavailable as exc:
                print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
                return 2
            checks = {
                "completed": record.status == "completed",
                "primary_failed": server.state["calls"].count("blind/primary") >= 1,
                "fallback_used": server.state["calls"].count("blind/fallback") >= 2,
                "published": root_file.is_file(),
                "previewable": preview.entrypoint == "app/index.html",
                "browser_click": browser.get("result") == "Botão funcionando" and browser.get("status") == "Interação validada",
                "browser_validator_present": browser.get("validator", "playwright") in {"playwright", "jsdom-runtime"},
            }
            if not all(checks.values()):
                raise RuntimeError("blind mission checks failed: %s" % checks)
            print(json.dumps({"status": "PASS", "checks": checks, "validator": browser.get("validator", "playwright"), "calls": server.state["calls"]}, ensure_ascii=False, indent=2))
            return 0
        finally:
            if runtime is not None:
                runtime.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
