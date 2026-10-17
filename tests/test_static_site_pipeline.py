"""Contract tests: actual mission loop, scripted model only, no E2B or live provider."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.agent.static_site_pipeline import build_static_candidate
from olympus.routing.interfaces import RoutingExecutionResult


class OneSelector:
    def select_candidates(self, task):
        return ("mock/rosales",)


class ScriptedRouter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def execute(self, model_id, prompt, **kwargs):
        self.calls.append(model_id)
        if not self.outputs:
            raise RuntimeError("mock provider exhausted")
        action = self.outputs.pop(0)
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model=model_id,
            provider="mock",
            output=json.dumps(action, ensure_ascii=False),
            latency_ms=1,
            cost=0.0,
            success=True,
        )


def action(kind, target=None, payload=None):
    return {"type": kind, "target": target, "payload": payload, "reason": "scripted test only"}


class StaticPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.deliveries = self.base / "deliveries"

    def build(self, router, name="rosales001"):
        return build_static_candidate(
            self.workspace, self.deliveries, name,
            "Crie uma landing page Rosales Café em site/index.html",
            router, selector=OneSelector(), max_iterations=5,
        )

    def test_scripted_agent_creates_and_preserves_site_without_browser(self):
        html = ("<!doctype html><html lang='pt-BR'><head>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>Rosales Café</title></head><body><main>"
                "<h1>Rosales Café</h1><p>O melhor café brasileiro ao estilo Colombiano.</p>"
                "</main></body></html>")
        router = ScriptedRouter([
            action("create_file", "site/index.html", html),
            action("finish", payload="completed"),
        ])
        with patch("olympus.agent.browser_delivery.WebDeliveryVerifier.verify",
                   side_effect=AssertionError("browser called on untrusted JS")):
            report = self.build(router)
        self.assertEqual(report["status"], "ARTIFACT_VERIFIED", report)
        self.assertFalse(report["model_inference_verified"])
        self.assertFalse(report["browser_verified"])
        self.assertFalse(report["visual_reviewed"])
        self.assertTrue(router.calls)
        saved = self.deliveries / "rosales001" / "site" / "index.html"
        self.assertEqual(saved.read_text(encoding="utf-8"), html + "\n")
        manifest = json.loads((saved.parent.parent / "manifest.json").read_text())
        self.assertEqual(manifest["files"][0]["sha256"],
                         hashlib.sha256(saved.read_bytes()).hexdigest())

    def test_no_existing_output_can_be_claimed_as_model_output(self):
        (self.workspace / "site").mkdir()
        (self.workspace / "site/index.html").write_text("prebuilt")
        router = ScriptedRouter([])
        with self.assertRaisesRegex(ValueError, "fresh empty workspace"):
            self.build(router)
        self.assertEqual(router.calls, [])
        self.assertFalse(self.deliveries.exists())

    def test_agent_attempt_to_run_code_is_blocked_and_not_delivered(self):
        router = ScriptedRouter([
            action("run_test", "tests.test_unsafe", ["tests.test_unsafe"]),
            action("finish", payload="finished"),
        ])
        with patch("olympus.agent.test_runner.TargetedTestRunner.run_unittest",
                   side_effect=AssertionError("host subprocess attempted")):
            report = self.build(router)
        self.assertEqual(report["status"], "BLOCKED", report)
        self.assertFalse((self.deliveries / "rosales001").exists())

    def test_invalid_external_html_is_not_preserved(self):
        router = ScriptedRouter([
            action("create_file", "site/index.html",
                   '<script src="https://tracker.invalid/a.js"></script>'),
            action("finish", payload="completed"),
        ])
        report = self.build(router)
        self.assertEqual(report["status"], "BLOCKED", report)
        self.assertFalse((self.deliveries / "rosales001").exists())

    def test_duplicate_mission_and_invalid_id_blocked_before_provider(self):
        for ident in ("../bad", "semi;colon", ""):
            with self.subTest(ident=ident):
                with self.assertRaisesRegex(ValueError, "mission ID"):
                    self.build(ScriptedRouter([]), ident)
        (self.deliveries / "rosales001").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.build(ScriptedRouter([]))

if __name__ == "__main__":
    unittest.main()
