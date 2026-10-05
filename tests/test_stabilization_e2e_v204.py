import json
import tempfile
import time
import unittest
from pathlib import Path

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.runtime import CloudRuntime
from olympus.routing.interfaces import RoutingExecutionResult


PROFESSIONAL_PAGE = (
    "<!doctype html><html lang='pt-BR'><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Olympus Tecnologia</title><style>"
    ":root{--bg:#07111f;--panel:#10233b;--text:#eff8ff;--accent:#38bdf8}*{box-sizing:border-box}"
    "body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:Arial,sans-serif;line-height:1.6}"
    "nav,main,footer{width:min(1080px,calc(100% - 2rem));margin:auto}nav{display:flex;justify-content:space-between;padding:1.5rem 0}"
    "a,button{display:inline-block;padding:.8rem 1.1rem;border-radius:.7rem;background:var(--accent);color:#06263a;text-decoration:none;border:0;font-weight:bold}"
    "section{padding:3rem 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}.card{padding:1.4rem;border-radius:1rem;background:var(--panel)}"
    "footer{padding:2rem 0;color:#a8c0d4}@media(max-width:700px){.grid{grid-template-columns:1fr}section{padding:2rem 0}}"
    "</style></head><body><nav><strong>Olympus</strong><a href='#contato'>Contato</a></nav><main>"
    "<section><h1>Entrega segura para empresas de tecnologia</h1><p>Transformamos objetivos complexos em experiências digitais claras, confiáveis e prontas para crescer.</p></section>"
    "<section><h2>Uma base completa para avançar</h2><div class='grid'><article class='card'>Estratégia orientada ao usuário.</article>"
    "<article class='card'>Engenharia validada em cada etapa.</article><article class='card'>Evolução contínua sem perder versões.</article></div></section>"
    "<section id='contato'><h2>Construa o próximo produto com confiança</h2><p>Conte sua meta e receba uma entrega verificável, preservada e preparada para publicação.</p><button>Começar agora</button></section>"
    "</main><footer>Olympus · Tecnologia responsável</footer></body></html>"
)


class BudgetThenResumeRouter:
    """Reproduce the two failures observed on the Mac, then complete safely."""

    def __init__(self):
        self.calls = 0
        self.resume_mode = False
        self.resume_prompt = ""

    @staticmethod
    def _result(output):
        return RoutingExecutionResult(
            requested_model="openrouter/openrouter/free",
            actual_model="openrouter/free-model",
            provider="openrouter",
            output=output,
            latency_ms=1,
            cost=0.0,
            success=True,
        )

    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        if self.resume_mode:
            self.resume_prompt = prompt
            return self._result(
                '{"type":"finish","target":null,"payload":"ready","reason":"verified"}'
            )
        if self.calls == 1:
            return self._result(json.dumps({'type': 'create_file', 'target': 'docs/delivery-concept.md', 'payload': '# Visual thesis\nA clear brand composition with restrained color, deliberate typography and readable spacing.\n# Content plan\nBrand, offer, detail and primary action.\n# Interaction plan\nNavigation and controls follow the requested workflow.\n# Evidence\nSynthetic fixture only. No claims about a real business. Browser and visual review pending.\n', 'reason': 'define the delivery concept'}))
        if self.calls <= 3:
            # Both the original and repair response omit target. The planner
            # must recover the complete document instead of losing the work.
            return self._result(
                '{"type":"create_file","payload":' + json.dumps(PROFESSIONAL_PAGE) +
                ',"reason":"create the requested page"}'
            )
        return self._result(
            '{"type":"search_code","target":"app","payload":"missing-marker",'
            '"reason":"continue searching before completion"}'
        )


class TimeoutThenSuccessRouter:
    def __init__(self):
        self.calls = 0

    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="openrouter",
                output="",
                latency_ms=180000,
                cost=0.0,
                success=False,
                error="Timeout: the model did not respond within 180 seconds",
                status="timeout",
            )
        if self.calls == 2:
            output = json.dumps({'type': 'create_file', 'target': 'docs/delivery-concept.md', 'payload': '# Visual thesis\nA clear brand composition with restrained color, deliberate typography and readable spacing.\n# Content plan\nBrand, offer, detail and primary action.\n# Interaction plan\nNavigation and controls follow the requested workflow.\n# Evidence\nSynthetic fixture only. No claims about a real business. Browser and visual review pending.\n', 'reason': 'define the delivery concept'})
        else:
            output = (
            '{"type":"create_file","target":"app/index.html",'
            '"payload":' + json.dumps(PROFESSIONAL_PAGE.replace("Entrega segura", "Second free model succeeded")) + ','
            '"reason":"create"}'
            if self.calls == 3
            else '{"type":"finish","target":null,"payload":"ready","reason":"verified"}'
        )
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model="another/free-model",
            provider="openrouter",
            output=output,
            latency_ms=1,
            cost=0.0,
            success=True,
        )


class StabilizationEndToEndV204Tests(unittest.TestCase):
    @staticmethod
    def _wait(runtime, execution_id, statuses, timeout=5.0):
        deadline = time.time() + timeout
        record = runtime.get(execution_id)
        while record is not None and record.status not in statuses and time.time() < deadline:
            time.sleep(0.02)
            record = runtime.get(execution_id)
        return record

    def test_iteration_boundary_verifies_publishes_and_previews_without_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = BudgetThenResumeRouter()
            runtime = CloudRuntime(
                tmp,
                lambda workspace, telemetry: AutonomousDeveloper(
                    workspace, router, telemetry=telemetry
                ),
                max_workers=1,
            )
            self.addCleanup(runtime.close)

            submitted = runtime.submit(
                "mac-e2e",
                "Crie uma landing page profissional do Olympus",
                max_iterations=12,
                project_name="Mac E2E",
            )
            completed = self._wait(
                runtime, submitted.execution_id, {"blocked", "failed", "completed"}
            )
            self.assertIsNotNone(completed)
            self.assertEqual(completed.status, "completed")
            self.assertIsNone(completed.error)
            workspace = Path(completed.workspace)
            self.assertIn("Entrega segura", (workspace / "app/index.html").read_text(encoding="utf-8"))

            project_file = Path(runtime.projects.project_root("mac-e2e"), "app/index.html")
            self.assertIn("Entrega segura", project_file.read_text(encoding="utf-8"))
            events = runtime.events(submitted.execution_id)
            self.assertTrue(any(event["event"] == "result_published" for event in events))
            self.assertFalse(any(event["event"] == "resumed" for event in events))
            self.assertEqual(len(runtime.versions.list("mac-e2e")), 2)

            previews = ProjectPreviewSessions(runtime.projects)
            session = previews.create("mac-e2e")
            _, preview_path = previews.resolve(session.token)
            self.assertEqual(preview_path.name, "index.html")
            self.assertIn("Entrega segura", preview_path.read_text(encoding="utf-8"))
            self.assertTrue(runtime.projects.export_zip("mac-e2e").is_file())

    def test_timeout_automatically_sequences_another_free_model_and_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = TimeoutThenSuccessRouter()
            runtime = CloudRuntime(
                tmp,
                lambda workspace, telemetry: AutonomousDeveloper(
                    workspace, router, telemetry=telemetry
                ),
                max_workers=1,
            )
            self.addCleanup(runtime.close)
            submitted = runtime.submit(
                "automatic-failover",
                "Crie uma landing page profissional",
                max_iterations=24,
            )
            completed = self._wait(
                runtime, submitted.execution_id, {"blocked", "failed", "completed"}
            )
            self.assertIsNotNone(completed)
            self.assertEqual(completed.status, "completed")
            self.assertEqual(router.calls, 4)
            events = runtime.events(submitted.execution_id)
            failover = next(event for event in events if event["event"] == "model_failover")
            self.assertTrue(failover["dynamic_route_retry"])
            project_file = Path(
                runtime.projects.project_root("automatic-failover"), "app/index.html"
            )
            self.assertIn("Second free model succeeded", project_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
