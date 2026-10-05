#!/usr/bin/env python3
"""Deterministic investor smoke test for the complete Olympus web mission flow."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread
import time
from typing import Optional
from urllib.request import urlopen

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.runtime import CloudRuntime
from olympus.routing.interfaces import RoutingExecutionResult


TASK = (
    "Crie uma landing page profissional e responsiva para o Olympus, em português, "
    "com identidade escura e destaque azul, menu superior, proposta de valor, três "
    "benefícios, fluxo Planejar → Construir → Testar → Publicar, comparação com o "
    "trabalho manual, depoimento, formulário de contato funcional e rodapé completo."
)

PLACEHOLDER = "<!doctype html><html><body><h1>Welcome</h1></body></html>"

LANDING_PAGE = r'''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Olympus transforma objetivos em produtos digitais verificados e prontos para apresentar.">
  <title>Olympus — Da ideia ao produto funcionando</title>
  <style>
    :root{color-scheme:dark;--bg:#07101c;--surface:#0d1928;--line:#1e354b;--text:#f5f9ff;--muted:#9aadc0;--cyan:#58d7ff;--blue:#3688ff;--green:#54e6a0;--shadow:0 24px 80px rgba(0,0,0,.34)}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 78% 8%,rgba(54,136,255,.18),transparent 32%),var(--bg);color:var(--text);font:16px/1.6 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:inherit;text-decoration:none}button,input{font:inherit}a:focus-visible,button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--cyan);outline-offset:3px}.container{width:min(1120px,calc(100% - 40px));margin:auto}.nav{display:flex;align-items:center;justify-content:space-between;min-height:78px;border-bottom:1px solid rgba(255,255,255,.08)}.brand{display:flex;align-items:center;gap:12px;font-weight:900;font-style:italic;letter-spacing:.18em}.mark{display:grid;place-items:center;width:34px;height:34px;border:1px solid rgba(88,215,255,.35);border-radius:11px;background:linear-gradient(145deg,rgba(88,215,255,.22),rgba(54,136,255,.06));color:var(--cyan)}.links{display:flex;align-items:center;gap:28px;color:var(--muted);font-size:14px}.links a:hover{color:var(--text)}.button{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:12px;padding:12px 18px;background:linear-gradient(135deg,var(--cyan),var(--blue));color:#03111d;font-weight:800;box-shadow:0 12px 38px rgba(54,136,255,.22);cursor:pointer}.button.secondary{border:1px solid var(--line);background:rgba(255,255,255,.035);box-shadow:none;color:var(--text)}details.mobile{display:none}.hero{display:grid;grid-template-columns:1.12fr .88fr;align-items:center;gap:70px;min-height:680px;padding:76px 0}.eyebrow{display:inline-flex;align-items:center;gap:9px;color:var(--cyan);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.14em}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 18px var(--green)}h1{margin:18px 0 22px;font-size:clamp(44px,6vw,76px);line-height:1.02;letter-spacing:-.055em}.gradient{color:transparent;background:linear-gradient(105deg,#fff 10%,var(--cyan) 60%,#76a9ff);background-clip:text;-webkit-background-clip:text}.lead{max-width:640px;color:var(--muted);font-size:19px}.actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:32px}.proof{display:flex;flex-wrap:wrap;gap:22px;margin-top:34px;color:#b7c5d4;font-size:13px}.proof span::before{content:"✓";margin-right:8px;color:var(--green)}.console{position:relative;border:1px solid var(--line);border-radius:24px;background:linear-gradient(145deg,rgba(17,33,51,.98),rgba(7,16,28,.95));padding:20px;box-shadow:var(--shadow);overflow:hidden}.console::before{content:"";position:absolute;inset:-30% 28% auto -30%;height:220px;background:rgba(88,215,255,.12);filter:blur(50px)}.console-head,.route{position:relative;display:flex;align-items:center;justify-content:space-between}.console-head{padding-bottom:16px;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}.online{color:var(--green)}.mission{position:relative;margin:18px 0;padding:18px;border:1px solid rgba(255,255,255,.08);border-radius:16px;background:rgba(255,255,255,.035)}.mission small{color:var(--cyan)}.mission strong{display:block;margin-top:8px;font-size:18px}.routes{position:relative;display:grid;gap:10px}.route{padding:12px 14px;border-radius:12px;background:rgba(255,255,255,.035);font-size:13px}.route b{font-weight:650}.route em{font-style:normal;color:var(--muted)}.route.active{border:1px solid rgba(84,230,160,.25)}.route.active em{color:var(--green)}section{padding:86px 0}.section-head{max-width:690px;margin-bottom:36px}.section-head span{color:var(--cyan);font-size:13px;font-weight:750;text-transform:uppercase;letter-spacing:.14em}h2{margin:10px 0 12px;font-size:clamp(32px,4vw,48px);line-height:1.12;letter-spacing:-.035em}.section-head p,.card p,.compare p,.quote p{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{min-height:220px;padding:26px;border:1px solid var(--line);border-radius:20px;background:rgba(255,255,255,.028)}.number{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:rgba(88,215,255,.1);color:var(--cyan);font-weight:850}.card h3{margin:24px 0 8px}.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;counter-reset:flow}.step{position:relative;padding:24px 20px;border-top:2px solid var(--blue);background:linear-gradient(180deg,rgba(54,136,255,.1),transparent)}.step::before{counter-increment:flow;content:"0" counter(flow);display:block;margin-bottom:24px;color:var(--cyan);font-weight:800}.compare{display:grid;grid-template-columns:1fr 1fr;gap:18px}.compare article{padding:30px;border:1px solid var(--line);border-radius:22px}.compare article:last-child{background:linear-gradient(145deg,rgba(54,136,255,.13),rgba(88,215,255,.04));border-color:rgba(88,215,255,.28)}.compare ul{padding:0;list-style:none}.compare li{margin:14px 0;color:var(--muted)}.compare li::before{content:"—";margin-right:10px;color:#64778a}.compare article:last-child li::before{content:"✓";color:var(--green)}.quote{display:grid;grid-template-columns:auto 1fr;gap:22px;align-items:start;padding:34px;border:1px solid var(--line);border-radius:22px;background:var(--surface)}.avatar{display:grid;place-items:center;width:54px;height:54px;border-radius:50%;background:linear-gradient(135deg,var(--cyan),var(--blue));color:#07101c;font-weight:900}.quote blockquote{margin:0;font-size:21px;line-height:1.45}.quote p{margin:10px 0 0;font-size:13px}.cta{display:grid;grid-template-columns:1fr .9fr;gap:40px;align-items:center;padding:42px;border:1px solid rgba(88,215,255,.24);border-radius:26px;background:linear-gradient(120deg,rgba(54,136,255,.14),rgba(88,215,255,.035))}.form{display:grid;gap:12px}.form label{font-size:13px;color:#c3d0dc}.form input{width:100%;margin-top:6px;padding:13px 14px;border:1px solid var(--line);border-radius:11px;background:#091522;color:var(--text)}.form-status{min-height:22px;margin:0;color:var(--green);font-size:13px}.footer{display:flex;justify-content:space-between;gap:20px;padding:30px 0 40px;border-top:1px solid rgba(255,255,255,.08);color:#718397;font-size:13px}
    @media(max-width:820px){.desktop-links{display:none}details.mobile{display:block;position:relative}details.mobile summary{cursor:pointer;list-style:none;color:var(--muted)}details.mobile nav{position:absolute;right:0;top:38px;z-index:2;display:grid;gap:12px;width:210px;padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:var(--shadow)}.hero{grid-template-columns:1fr;gap:40px;min-height:auto;padding:64px 0}.cards,.flow,.compare,.cta{grid-template-columns:1fr}.flow{gap:8px}.cta{padding:28px}.quote{grid-template-columns:1fr}.footer{flex-direction:column}.container{width:min(100% - 28px,1120px)}}
    @media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{animation:none!important;transition:none!important}}
  </style>
</head>
<body>
  <header class="container nav"><a class="brand" href="#inicio" aria-label="Olympus, início"><span class="mark" aria-hidden="true">Ω</span>OLYMPUS</a><nav class="links desktop-links" aria-label="Navegação principal"><a href="#beneficios">Benefícios</a><a href="#processo">Como funciona</a><a href="#comparacao">Comparação</a><a class="button" href="#contato">Começar um projeto</a></nav><details class="mobile"><summary aria-label="Abrir menu">Menu</summary><nav aria-label="Navegação móvel"><a href="#beneficios">Benefícios</a><a href="#processo">Como funciona</a><a href="#comparacao">Comparação</a><a href="#contato">Começar</a></nav></details></header>
  <main id="inicio">
    <section class="container hero"><div><span class="eyebrow"><i class="dot"></i>Orquestração inteligente em operação</span><h1>Transforme ideias em <span class="gradient">produtos que funcionam.</span></h1><p class="lead">O Olympus planeja, constrói, testa e publica experiências digitais com múltiplas IAs trabalhando como uma única equipe.</p><div class="actions"><a class="button" href="#contato">Começar um projeto</a><a class="button secondary" href="#processo">Conhecer o processo</a></div><div class="proof"><span>Fallback automático</span><span>Verificação contínua</span><span>Resultado preservado</span></div></div><aside class="console" aria-label="Demonstração do roteamento Olympus"><div class="console-head"><span>Missão em andamento</span><span class="online">● Sistema operacional</span></div><div class="mission"><small>OBJETIVO</small><strong>Criar uma experiência pronta para apresentar</strong></div><div class="routes"><div class="route"><b>Rota primária</b><em>Limite detectado</em></div><div class="route active"><b>Groq · alternativa</b><em>Executando</em></div><div class="route"><b>Validação Olympus</b><em>Próxima etapa</em></div></div></aside></section>
    <section id="beneficios" class="container"><div class="section-head"><span>Uma plataforma, várias inteligências</span><h2>Menos tentativas. Mais entrega.</h2><p>O usuário descreve o resultado esperado; o Olympus coordena a complexidade técnica nos bastidores.</p></div><div class="cards"><article class="card"><span class="number">01</span><h3>Automação inteligente</h3><p>Seleciona a rota adequada, acompanha o trabalho e troca de IA quando encontra indisponibilidade.</p></article><article class="card"><span class="number">02</span><h3>Qualidade verificável</h3><p>Revisa conteúdo, estrutura, responsividade e integridade antes de permitir a conclusão.</p></article><article class="card"><span class="number">03</span><h3>Continuidade segura</h3><p>Preserva arquivos, versões e progresso entre tentativas para que nenhuma falha apague o resultado.</p></article></div></section>
    <section id="processo" class="container"><div class="section-head"><span>Fluxo completo</span><h2>Da intenção à apresentação.</h2></div><div class="flow"><article class="step"><h3>Planejar</h3><p>Entende o objetivo e organiza requisitos.</p></article><article class="step"><h3>Construir</h3><p>Produz arquivos e interfaces completas.</p></article><article class="step"><h3>Testar</h3><p>Valida conteúdo, código e experiência.</p></article><article class="step"><h3>Publicar</h3><p>Entrega preview, versão e download.</p></article></div></section>
    <section id="comparacao" class="container"><div class="section-head"><span>Diferença prática</span><h2>Um novo modo de construir.</h2></div><div class="compare"><article><h3>Trabalho fragmentado</h3><ul><li>Várias ferramentas desconectadas</li><li>Recomeço depois de cada falha</li><li>Validação manual no final</li><li>Erros técnicos expostos ao usuário</li></ul></article><article><h3>Trabalho com Olympus</h3><ul><li>Uma conversa conduz todo o processo</li><li>Fallback preserva o progresso</li><li>Qualidade verificada a cada ciclo</li><li>Entrega pronta para visualizar</li></ul></article></div></section>
    <section class="container"><div class="quote"><div class="avatar" aria-hidden="true">MR</div><div><blockquote>“O Olympus transformou uma ideia ampla em uma entrega clara, testada e pronta para decisão.”</blockquote><p>Marina Rocha · Diretora de Produto, empresa demonstrativa</p></div></div></section>
    <section id="contato" class="container"><div class="cta"><div><span class="eyebrow">Próximo projeto</span><h2>Veja o Olympus construir.</h2><p class="lead">Solicite uma demonstração e acompanhe uma missão completa, da ideia ao preview.</p></div><form id="demo-form" class="form"><label>Nome<input name="nome" autocomplete="name" required placeholder="Como podemos chamar você?"></label><label>E-mail<input name="email" type="email" autocomplete="email" required placeholder="voce@empresa.com"></label><button class="button" type="submit">Solicitar demonstração</button><p id="form-status" class="form-status" role="status" aria-live="polite"></p></form></div></section>
  </main>
  <footer class="container footer"><span>© 2026 Olympus. Inteligência coordenada, resultado verificável.</span><span>Privacidade · Segurança · Contato</span></footer>
  <script>const form=document.getElementById("demo-form");form.addEventListener("submit",function(event){event.preventDefault();document.getElementById("form-status").textContent="Solicitação registrada. Nossa equipe entrará em contato.";form.reset();});</script>
</body>
</html>'''


class DemoSelector:
    def select_candidates(self, _task):
        return ("omniroute::primary-free", "groq::investor-demo")


class DemoRouter:
    """Simulates one provider failure and a repairing fallback provider."""
    def __init__(self):
        self.primary_calls = 0
        self.fallback_calls = 0

    def execute(self, model_id, _prompt, **_kwargs):
        if model_id.startswith("omniroute::"):
            self.primary_calls += 1
            if self.primary_calls == 1:
                action = {"type": "create_file", "target": "app/index.html", "payload": PLACEHOLDER, "reason": "first safe draft"}
                return RoutingExecutionResult(
                    model_id, "primary-free", "omniroute", json.dumps(action),
                    2, 0.0, True, None, {}, "success",
                )
            return RoutingExecutionResult(
                model_id, "", "omniroute", "", 2, 0.0, False,
                "rate limit reached", {"http_status": 429}, "rate_limited",
            )
        self.fallback_calls += 1
        sequence = (
            {'type': 'create_file', 'target': 'docs/delivery-concept.md', 'payload': '# Visual thesis\nA clear brand composition with restrained color, deliberate typography and readable spacing.\n# Content plan\nBrand, offer, detail and primary action.\n# Interaction plan\nNavigation and controls follow the requested workflow.\n# Evidence\nSynthetic fixture only. No claims about a real business. Browser and visual review pending.\n', 'reason': 'define the delivery concept'},
            {"type": "patch_file", "target": "app/index.html", "payload": {
                "operation": "replace_lines", "start_line": 1, "end_line": 1,
                "new_content": LANDING_PAGE,
            }, "reason": "repair every quality finding"},
            {"type": "finish", "target": None, "payload": None, "reason": "verified professional result"},
        )
        action = sequence[min(self.fallback_calls - 1, len(sequence) - 1)]
        return RoutingExecutionResult(
            model_id, "investor-demo", "groq", json.dumps(action, ensure_ascii=False),
            3, 0.0, True, None, {}, "success",
        )


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


def _wait(runtime: CloudRuntime, execution_id: str, timeout: float = 8.0):
    deadline = time.time() + timeout
    record = runtime.get(execution_id)
    while record and record.status not in {"completed", "failed", "blocked", "cancelled"} and time.time() < deadline:
        time.sleep(0.02)
        record = runtime.get(execution_id)
    if record is None or record.status != "completed":
        raise RuntimeError("mission did not complete: %s" % getattr(record, "error", "timeout"))
    return record


def _serve_and_fetch(directory: Path) -> tuple[int, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen("http://127.0.0.1:%d/index.html" % server.server_port, timeout=3) as response:
            return response.status, response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _verify_interaction(source: str) -> bool:
    if not shutil.which("node"):
        return False
    start = source.rfind("<script>")
    end = source.rfind("</script>")
    if start < 0 or end <= start:
        return False
    script = source[start + len("<script>"):end]
    harness = r'''
const vm=require("node:vm"),fs=require("node:fs");let handler=null,prevented=false,reset=false;
const status={textContent:""};const form={addEventListener:(name,fn)=>{if(name==="submit")handler=fn},reset:()=>{reset=true}};
const document={getElementById:(id)=>id==="demo-form"?form:id==="form-status"?status:null};
vm.runInNewContext(fs.readFileSync(0,"utf8"),{document});if(!handler)process.exit(2);
handler({preventDefault:()=>{prevented=true}});if(!prevented||!reset||!status.textContent.includes("registrada"))process.exit(3);
'''
    completed = subprocess.run(
        ["node", "-e", harness], input=script, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False,
    )
    return completed.returncode == 0


def run_smoke(output: Optional[Path] = None) -> dict:
    temporary = tempfile.TemporaryDirectory(prefix="olympus-investor-smoke-")
    data_dir = Path(temporary.name)
    captured = {}
    router = DemoRouter()

    class CapturingRunner:
        def __init__(self, workspace, telemetry):
            self.developer = AutonomousDeveloper(
                workspace, router, selector=DemoSelector(), telemetry=telemetry,
            )

        def run(self, task, max_iterations=12, resume=True):
            report = self.developer.run(task, max_iterations=max_iterations, resume=resume)
            captured["report"] = report
            return report

    runtime = CloudRuntime(data_dir, lambda workspace, telemetry: CapturingRunner(workspace, telemetry), max_workers=1)
    try:
        execution = runtime.submit("investor-demo", TASK, max_iterations=10, project_name="Olympus Investor Demo")
        record = _wait(runtime, execution.execution_id)
        previews = ProjectPreviewSessions(runtime.projects)
        preview = previews.create("investor-demo")
        _, preview_file = previews.resolve(preview.token)
        http_status, served = _serve_and_fetch(preview_file.parent)
        interaction_ok = _verify_interaction(served)
        archive = runtime.projects.export_zip("investor-demo")
        events = runtime.events(execution.execution_id)
        report = captured["report"]

        checks = {
            "mission_completed": record.status == "completed",
            "cross_provider_failover": any(item.get("event") == "model_failover" and item.get("cross_provider") for item in events),
            "compiled_without_ai": any(item.get("event") == "mission_compiled" for item in events),
            "checkpoint_handoff": any(
                item.get("event") == "model_resume" and "app/index.html" in item.get("files_modified", [])
                for item in events
            ),
            "quality_repair": router.fallback_calls >= 2 and "Welcome" not in served,
            "published": any(item.get("event") == "result_published" for item in events),
            "preview_resolved": preview.entrypoint == "app/index.html" and preview_file.is_file(),
            "http_200": http_status == 200,
            "responsive": "@media(max-width:820px)" in served and 'name="viewport"' in served,
            "accessible": 'lang="pt-BR"' in served and 'aria-live="polite"' in served,
            "interaction": interaction_ok,
            "requested_sections": all(token in served for token in (
                "<nav", "Planejar", "Construir", "Testar", "Publicar",
                "Trabalho fragmentado", "blockquote", 'id="demo-form"', "<footer",
            )),
            "no_external_dependencies": not any(token in served for token in (
                "https://cdn", "unpkg.com", "jsdelivr.net", "<script src=",
            )),
            "no_placeholders": not any(token in served.lower() for token in (
                "lorem ipsum", "coming soon", "<!-- todo", "welcome",
            )),
            "download_ready": archive.is_file() and archive.stat().st_size > 0,
            "versioned": len(runtime.versions.list("investor-demo")) == 2,
        }
        if not all(checks.values()):
            raise RuntimeError("smoke checks failed: %s" % [name for name, passed in checks.items() if not passed])

        if output is not None:
            target = Path(output).resolve()
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preview_file, target / "index.html")
            shutil.copy2(archive, target / "olympus-investor-demo.zip")

        return {
            "status": "PASS",
            "execution_id": record.execution_id,
            "models_attempted": list(report.models_attempted),
            "iterations": report.iterations,
            "entrypoint": preview.entrypoint,
            "checks": checks,
        }
    finally:
        runtime.close()
        temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="copy the verified landing page and ZIP to this directory")
    args = parser.parse_args()
    result = run_smoke(args.output)
    if args.output is not None:
        report_path = args.output.resolve() / "smoke-report.json"
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
