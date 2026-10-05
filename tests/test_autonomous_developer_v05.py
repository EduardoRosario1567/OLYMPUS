import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.agent.control_plane import AgentControlPlane
from olympus.agent.loop import AgentLoop
from olympus.agent.mission import AutonomousPatchRunner


class ScriptedPlanner:
    def __init__(self, actions):
        self.actions = list(actions)
    def next_action(self, *args, **kwargs):
        return self.actions.pop(0)


class DummyRouter:
    pass


class Selector:
    def select_candidates(self, task):
        return ("model/a",)


class TestAutonomousDeveloperV05(unittest.TestCase):
    def test_targetless_objective_becomes_auto_mission(self):
        mission = AutonomousDeveloper.mission_for("Improve startup UX")
        self.assertEqual(mission.steps[0].id, "AUTO-1")
        self.assertTrue(mission.metadata["targetless"])
        self.assertIn("Improve startup UX", mission.steps[0].instruction)

    def test_empty_objective_is_rejected(self):
        with self.assertRaises(ValueError):
            AutonomousDeveloper.mission_for("   ")

    def test_end_to_end_create_test_finish_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "olympus").mkdir()
            (root / "olympus" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            actions = [
                AgentAction(ActionType.CREATE_FILE, "olympus/value.py", "def value():\n    return 7\n", "create"),
                AgentAction(ActionType.CREATE_FILE, "tests/test_value.py", "import unittest\nfrom olympus.value import value\nclass T(unittest.TestCase):\n    def test_value(self): self.assertEqual(value(), 7)\n", "test"),
                AgentAction(ActionType.RUN_TEST, "tests.test_value", ["tests.test_value"], "run"),
                AgentAction(ActionType.FINISH, reason="done"),
            ]
            planner = ScriptedPlanner(actions)
            runner = AutonomousPatchRunner(
                str(root), DummyRouter(), selector=Selector(),
                planner_factory=lambda router, model: planner,
                loop_factory=lambda r, p: AgentLoop(r, p),
            )
            dev = AutonomousDeveloper.__new__(AutonomousDeveloper)
            dev.root = str(root)
            dev.runner = runner
            report = dev.run("Create a value function with tests", resume=False)
            self.assertTrue(report.success)
            self.assertEqual(report.status, "completed")
            self.assertIn("olympus/value.py", report.files_modified)
            self.assertIn("tests.test_value", report.tests_run)
            self.assertEqual(report.models_attempted, ("model/a",))

    def test_report_preserves_failure_without_claiming_success(self):
        mission = AutonomousDeveloper.mission_for("x")
        self.assertEqual(mission.metadata["mode"], "autonomous_developer")
