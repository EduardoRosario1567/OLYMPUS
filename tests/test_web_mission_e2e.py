import tempfile
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.cloud.runtime import CloudRuntime
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.routing.interfaces import RoutingExecutionResult


class ScriptedFreeRouter:
    def __init__(self):
        self.calls = 0

    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = json.dumps({'type': 'create_file', 'target': 'docs/delivery-concept.md', 'payload': '# Visual thesis\nA clear brand composition with restrained color, deliberate typography and readable spacing.\n# Content plan\nBrand, offer, detail and primary action.\n# Interaction plan\nNavigation and controls follow the requested workflow.\n# Evidence\nSynthetic fixture only. No claims about a real business. Browser and visual review pending.\n', 'reason': 'define the delivery concept'})
        elif self.calls == 2:
            output = (
                '{"type":"create_file","payload":{'
                '"path":"app/index.html",'
                '"content":"<!doctype html><html lang=\\"pt-BR\\"><head><title>Busca Olympus</title>'
                '<meta name=\\"viewport\\" content=\\"width=device-width,initial-scale=1\\"><style>'
                '*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#101114;color:#f7f7f8;font-family:Arial,sans-serif}'
                'main{width:min(680px,calc(100% - 2rem));text-align:center}h1{font-size:clamp(2rem,8vw,4rem);margin:0 0 1rem}'
                'p{color:#a8abb3}.search{display:flex;gap:.6rem;margin-top:2rem}input{flex:1;padding:1rem;border:1px solid #454854;border-radius:999px;background:#1d1f25;color:white}'
                'button{padding:0 1.4rem;border:0;border-radius:999px;background:#7dd3fc;color:#082f49;font-weight:bold}</style></head>'
                '<body><main><h1>Busca Olympus</h1><p>Encontre informações relevantes com rapidez e clareza.</p>'
                '<div class=\\"search\\"><input aria-label=\\"Pesquisar\\" placeholder=\\"Digite sua busca\\"><button>Pesquisar</button></div>'
                '</main></body></html>"},'
                '"reason":"create the interface"}'
            )
        else:
            output = (
                '{"type":"finish","target":null,"payload":"ready",'
                '"reason":"verified"}'
            )
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model="openrouter/free-model",
            provider="openrouter",
            output=output,
            latency_ms=1,
            cost=0.0,
            success=True,
        )


class TestWebMissionEndToEnd(unittest.TestCase):
    def test_startup_recovers_preview_from_legacy_completed_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = CloudRuntime(tmp, lambda workspace, telemetry: None, max_workers=1)
            seed.projects.ensure("legacy-preview", "Legacy Preview")
            record = seed.store.create(
                "legacy-preview",
                "legacy-mission",
                "Crie uma landing page HTML completa",
                tenant_id="local",
            )
            workspace = seed.projects.execution_workspace(
                "legacy-preview", record.execution_id
            )
            page = workspace / "app" / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                "<!doctype html><html lang=\"pt-BR\"><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Preview legado</title><style>body{font-family:Arial}main{max-width:720px;margin:auto}</style></head><body><main><h1>Preview legado recuperado</h1><p>Entrega validada para apresentação.</p><section><h2>Continuidade</h2><p>O trabalho preservado permanece disponível.</p></section><section><h2>Resultado</h2><p>Missão recuperada com sucesso.</p></section></main></body></html>",
                encoding="utf-8",
            )
            seed.store.update(
                record.execution_id,
                status="completed",
                workspace=str(workspace),
            )
            seed.close()

            recovered = CloudRuntime(tmp, lambda workspace, telemetry: None, max_workers=1)
            self.addCleanup(recovered.close)
            published = Path(
                recovered.projects.project_root("legacy-preview"),
                "app",
                "index.html",
            )
            self.assertIn("Preview legado recuperado", published.read_text(encoding="utf-8"))
            events = recovered.events(record.execution_id)
            self.assertTrue(any(item["event"] == "legacy_result_recovered" for item in events))
            session = ProjectPreviewSessions(recovered.projects).create("legacy-preview")
            self.assertEqual(session.entrypoint, "app/index.html")

    def test_completed_report_with_lost_file_list_is_recovered_before_preview(self):
        class LostReportRunner:
            def __init__(self, workspace):
                self.workspace = Path(workspace)

            def run(self, task, max_iterations=12, resume=True):
                target = self.workspace / "app" / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "<!doctype html><html lang=\"pt-BR\"><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Olympus recuperado</title><style>body{font-family:Arial}main{max-width:720px;margin:auto}</style></head><body><main><h1>Olympus recuperado</h1><p>Entrega verificada e pronta para apresentação.</p><section><h2>Continuidade</h2><p>O checkpoint preservou o trabalho.</p></section><section><h2>Resultado</h2><p>A missão foi retomada e publicada.</p></section></main></body></html>",
                    encoding="utf-8",
                )
                return SimpleNamespace(
                    status="completed", files_modified=(), error=None
                )

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(
                tmp,
                lambda workspace, telemetry: LostReportRunner(workspace),
                max_workers=1,
            )
            self.addCleanup(runtime.close)
            submitted = runtime.submit(
                "lost-report",
                "Crie uma landing page HTML do Olympus",
                project_name="Lost Report",
            )
            deadline = time.time() + 3
            record = submitted
            while record.status not in {"completed", "failed", "blocked"} and time.time() < deadline:
                time.sleep(0.02)
                record = runtime.get(submitted.execution_id)
            self.assertEqual(record.status, "completed")
            published = Path(runtime.projects.project_root("lost-report"), "app", "index.html")
            self.assertIn("Olympus recuperado", published.read_text(encoding="utf-8"))
            event = next(item for item in runtime.events(submitted.execution_id) if item["event"] == "result_published")
            self.assertEqual(event["files_recovered"], ["app/index.html"])
            session = ProjectPreviewSessions(runtime.projects).create("lost-report")
            self.assertEqual(session.entrypoint, "app/index.html")

    def test_web_mission_cannot_complete_without_a_previewable_page(self):
        class EmptyRunner:
            def run(self, task, max_iterations=12, resume=True):
                return SimpleNamespace(status="completed", files_modified=(), error=None)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(
                tmp,
                lambda workspace, telemetry: EmptyRunner(),
                max_workers=1,
            )
            self.addCleanup(runtime.close)
            submitted = runtime.submit(
                "empty-web",
                "Crie uma landing page HTML completa",
                project_name="Empty Web",
            )
            deadline = time.time() + 3
            record = submitted
            while record.status not in {"completed", "failed", "blocked"} and time.time() < deadline:
                time.sleep(0.02)
                record = runtime.get(submitted.execution_id)
            self.assertEqual(record.status, "failed")
            self.assertIn("completion_validation", record.error)
            events = runtime.events(submitted.execution_id)
            self.assertTrue(any(item["event"] == "completion_rejected" for item in events))
            self.assertFalse(any(item["event"] == "result_published" for item in events))

    def test_free_router_creates_verifies_and_completes_web_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ScriptedFreeRouter()
            developer = AutonomousDeveloper(tmp, router)

            report = developer.run(
                "Crie uma interface web de busca inspirada no Google",
                max_iterations=4,
                resume=False,
            )

            self.assertTrue(report.success)
            self.assertEqual(report.status, "completed")
            self.assertEqual(report.delivery_review["browser"], "pending")
            self.assertEqual(report.delivery_review["visual"], "pending")
            self.assertEqual(report.models_attempted, ("openrouter/openrouter/free",))
            self.assertIn("app/index.html", report.files_modified)
            self.assertTrue(Path(tmp, "app", "index.html").is_file())
            self.assertEqual(router.calls, 3)

    def test_cloud_runtime_publishes_and_exports_completed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(
                tmp,
                lambda workspace, telemetry: AutonomousDeveloper(
                    workspace, ScriptedFreeRouter(), telemetry=telemetry
                ),
                max_workers=1,
            )
            self.addCleanup(runtime.close)

            execution = runtime.submit(
                "google-demo",
                "Crie uma interface web de busca inspirada no Google",
                max_iterations=4,
                project_name="Google Demo",
            )
            deadline = time.time() + 3
            record = execution
            while record.status not in {"completed", "failed", "blocked"} and time.time() < deadline:
                time.sleep(0.02)
                record = runtime.get(execution.execution_id)

            self.assertEqual(record.status, "completed")
            project_root = runtime.projects.project_root("google-demo")
            self.assertTrue(Path(project_root, "app", "index.html").is_file())
            archive = runtime.projects.export_zip("google-demo")
            self.assertTrue(archive.is_file())
            published = next(event for event in runtime.events(execution.execution_id) if event["event"] == "result_published")
            self.assertTrue(published["version_id"])
            self.assertTrue(published["previous_version_id"])
            self.assertEqual(len(runtime.versions.list("google-demo")), 2)
            previews = ProjectPreviewSessions(runtime.projects)
            session = previews.create("google-demo")
            _, preview_path = previews.resolve(session.token)
            self.assertIn("Pesquisar", preview_path.read_text(encoding="utf-8"))
            _, safety = runtime.restore_project_version("google-demo", published["previous_version_id"])
            self.assertEqual(safety.reason, "pre_restore")
            self.assertFalse(Path(project_root, "app", "index.html").exists())


if __name__ == "__main__":
    unittest.main()
