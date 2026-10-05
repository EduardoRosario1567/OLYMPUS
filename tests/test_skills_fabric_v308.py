import json
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace

from olympus.agent.actions import ActionType
from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.agent.planner import ModelPlanner
from olympus.routing.interfaces import RoutingExecutionResult
from olympus.skills.fabric import SkillsFabric

ROOT = Path(__file__).resolve().parents[1]


def response(output, success=True, provider="fake-groq", actual="actual-model", error=None):
    return RoutingExecutionResult("requested", actual, provider, output, 1, 0.0, success,
                                  error=error, status="success" if success else "technical_failure")


class FakeRouter:
    def __init__(self, results):
        self.results = list(results)
        self.prompts = []

    def execute(self, model, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.results.pop(0)


class Selector:
    def select_candidates(self, task):
        return ("fake/a", "fake/b")


class SkillsFabricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "vendor", self.root / "vendor")
        self.fabric = SkillsFabric(self.root, "tenant-a")

    def test_provenance_and_catalog(self):
        c = self.fabric.catalog()
        self.assertTrue(c["healthy"])
        self.assertEqual(c["version"], "6.4.2")
        self.assertEqual(c["commit"], "8ca22dba9a94f28898bbce59f2537ff4d87c747d")
        self.assertEqual(len(c["skills"]), 15)
        self.assertEqual(sum(s["supported"] for s in c["skills"]), 6)
        self.assertFalse(c["hooks_enabled"])

    def test_selection_uses_action_state(self):
        self.assertEqual(self.fabric.choose("Crie código Python", {}), ("writing-plans",))
        self.assertEqual(self.fabric.choose("Corrija bug Python", {}), ("systematic-debugging", "verification-before-completion"))
        self.assertEqual(self.fabric.choose("Crie código Python", {"files_modified": ["x.py"]})[0], "test-driven-development")
        self.assertEqual(self.fabric.choose("Crie uma landing page", {"files_modified": ["app/index.html"]})[0], "executing-plans")
        self.assertEqual(self.fabric.choose("Crie código Python", {"files_modified": ["x.py"], "tests_run": ["tests.test_x"]})[0], "requesting-code-review")
        self.assertEqual(self.fabric.choose("Crie código Python", {"recent_errors": ["bad syntax"]})[0], "systematic-debugging")
        self.assertEqual(self.fabric.choose("Escreva uma mensagem de aniversário", {}), ())

    def test_context_is_bounded_and_preserves_policy(self):
        text, details, error = self.fabric.context("Corrija bug Python", "{}")
        self.assertIsNone(error)
        self.assertLess(len(text), 11000)
        self.assertIn("The user task", text)
        self.assertIn("JSON schema", text)
        self.assertIn("Do not invent tools", text)
        self.assertIn("ALWAYS find root cause", text)
        self.assertEqual(len(details), 2)

    def test_disabled_library_does_not_read_bundle(self):
        self.fabric.configure(enabled=False)
        shutil.rmtree(self.root / "vendor")
        self.assertEqual(self.fabric.context("Crie código Python", "{}"), ("", (), None))

    def test_per_skill_toggle(self):
        self.fabric.configure(disabled_skills=["writing-plans"])
        self.assertEqual(self.fabric.context("Crie código Python", "{}"), ("", (), None))
        self.fabric.configure(disabled_skills=[])
        self.assertTrue(self.fabric.context("Crie código Python", "{}")[0])

    def test_settings_do_not_cross_tenants(self):
        other = SkillsFabric(self.root, "tenant-b")
        self.fabric.configure(enabled=False)
        self.assertTrue(other.settings()["enabled"])
        self.assertFalse(self.fabric.settings()["enabled"])
        self.assertNotEqual(other.state_path, self.fabric.state_path)

    def test_invalid_settings_disable_library(self):
        self.fabric.configure(enabled=False)
        self.fabric.state_path.write_text("{broken")
        self.assertFalse(self.fabric.settings()["enabled"])
        self.assertEqual(self.fabric.context("Crie código Python", "{}"), ("", (), None))

    def test_invalid_config_rejected(self):
        for value in ("true", 1):
            with self.assertRaises(ValueError):
                self.fabric.configure(enabled=value)
        with self.assertRaises(ValueError):
            self.fabric.configure(disabled_skills=["../../arbitrary"])

    def test_corrupt_skill_falls_back_without_partial_context(self):
        p = self.root / "vendor/superpowers/6.4.2/skills/writing-plans/SKILL.md"
        p.write_text("modified payload")
        self.assertEqual(self.fabric.context("Crie código Python", "{}"), ("", (), "skill_context_unavailable"))
        self.assertFalse(self.fabric.catalog()["healthy"])

    def test_missing_bundle_and_invalid_state_fall_back(self):
        self.assertEqual(self.fabric.context("Crie código Python", "[]")[2], "skill_context_unavailable")
        (self.root / "vendor/superpowers/current.json").unlink()
        self.assertEqual(self.fabric.context("Crie código Python", "{}")[2], "skill_context_unavailable")

    def test_pointer_cannot_escape_vendor(self):
        (self.root / "vendor/superpowers/current.json").write_text(json.dumps({"version": "../../private"}))
        self.assertEqual(self.fabric.context("Crie código Python", "{}")[2], "skill_context_unavailable")

    def test_planner_keeps_allowed_action_schema_and_actual_provider(self):
        router = FakeRouter([response('{"type":"finish","reason":"verified"}')])
        events = []
        planner = ModelPlanner(router, "fake/route", self.fabric, events.append)
        action = planner.next_action("Crie código Python", "{}", SimpleNamespace(snippets={}), (ActionType.FINISH,))
        self.assertEqual(action.type, ActionType.FINISH)
        self.assertIn("OLYMPUS SKILLS FABRIC", router.prompts[0])
        applied = next(e for e in events if e["event"] == "skill_applied")
        self.assertEqual(applied["model"], "actual-model")
        self.assertEqual(applied["provider"], "fake-groq")
        self.assertEqual(applied["skill_version"], "6.4.2")

    def test_repair_context_survives_invalid_json(self):
        router = FakeRouter([response("invalid"), response('{"type":"finish","reason":"ok"}')])
        events = []
        action = ModelPlanner(router, "fake/route", self.fabric, events.append).next_action(
            "Crie código Python", "{}", SimpleNamespace(snippets={}), (ActionType.FINISH,))
        self.assertEqual(action.type, ActionType.FINISH)
        self.assertTrue(all("OLYMPUS SKILLS FABRIC" in p for p in router.prompts))
        self.assertEqual([e["phase"] for e in events if e["event"] == "skill_applied"], ["plan_action", "repair_action"])

    def test_skill_failure_does_not_fail_planner_or_expose_secret(self):
        class Broken:
            def context(self, *args):
                raise RuntimeError("secret should never appear")
        router = FakeRouter([response('{"type":"finish","reason":"ok"}')])
        events = []
        ModelPlanner(router, "fake/route", Broken(), events.append).next_action(
            "Crie código Python", "{}", SimpleNamespace(snippets={}), (ActionType.FINISH,))
        self.assertEqual(events[0]["event"], "skill_fallback")
        self.assertNotIn("secret", json.dumps(events))
        self.assertNotIn("OLYMPUS SKILLS FABRIC", router.prompts[0])

    def test_telemetry_failure_does_not_stop_action(self):
        def broken(event):
            raise RuntimeError("offline")
        router = FakeRouter([response('{"type":"finish","reason":"ok"}')])
        self.assertEqual(ModelPlanner(router, "fake/route", self.fabric, broken).next_action(
            "Crie código Python", "{}", SimpleNamespace(snippets={}), (ActionType.FINISH,)).type, ActionType.FINISH)

    def test_end_to_end_mission_with_provider_failover_and_skill_events(self):
        workspace = self.root / "workspace"
        (workspace / "olympus").mkdir(parents=True)
        (workspace / "olympus/__init__.py").write_text("")
        (workspace / "tests").mkdir()
        (workspace / "tests/__init__.py").write_text("")
        actions = [
            {"type": "create_file", "target": "olympus/value.py", "payload": "def value():\n    return 7\n", "reason": "implement"},
            {"type": "create_file", "target": "tests/test_value.py", "payload": "import unittest\nfrom olympus.value import value\nclass T(unittest.TestCase):\n    def test_value(self): self.assertEqual(value(), 7)\n", "reason": "test"},
            {"type": "run_test", "target": "tests.test_value", "payload": ["tests.test_value"], "reason": "verify"},
            {"type": "finish", "reason": "verified"},
        ]
        router = FakeRouter([response("", False, "fake-groq", error="Timeout: upstream unavailable")] +
                            [response(json.dumps(a), provider="fake-ollama", actual="recovery-model") for a in actions])
        events = []
        dev = AutonomousDeveloper(str(workspace), router, selector=Selector(), telemetry=events.append, skills_fabric=self.fabric)
        report = dev.run("Crie função Python value que retorna 7 com teste unittest", resume=False)
        self.assertTrue(report.success, report.error)
        self.assertEqual(report.models_attempted, ("fake/a", "fake/b"))
        self.assertIn("tests.test_value", report.tests_run)
        self.assertEqual((workspace / "olympus/value.py").read_text(), "def value():\n    return 7\n")
        self.assertTrue(any(e["event"] == "model_failover" for e in events))
        self.assertTrue(any(e["event"] == "skill_applied" and e["provider"] == "fake-ollama" for e in events))
        self.assertTrue(any(e.get("skill_id") == "test-driven-development" for e in events))


if __name__ == "__main__":
    unittest.main()
