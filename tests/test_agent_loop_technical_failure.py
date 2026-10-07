import tempfile
import unittest
from pathlib import Path

from types import SimpleNamespace

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.state import AgentState


class TimeoutPlanner:
    def __init__(self):
        self.calls = 0

    def next_action(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("timeout: timed out")


class TestAgentLoopTechnicalFailure(unittest.TestCase):
    def test_planner_timeout_blocks_model_attempt_as_technical(self):
        planner = TimeoutPlanner()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = AgentLoop(root=tmp, planner=planner).run(
                task="technical failure test",
                selected_model="model/a",
                max_iterations=4,
            )
        self.assertEqual(result.state.status.value, "blocked")
        self.assertEqual(result.failure_kind, "technical")
        self.assertEqual(planner.calls, 1)
        self.assertIn("timeout", " ".join(result.state.errors).lower())
        self.assertEqual(result.history[-1]["failure_kind"], "technical")


    def test_repeated_read_after_verifier_error_hands_off_before_budget_exhaustion(self):
        class ReadPlanner:
            def __init__(self):
                self.calls = 0

            def next_action(self, *args, **kwargs):
                self.calls += 1
                return AgentAction(ActionType.READ_FILE, "app/index.html")

        class Verifier:
            delivery_review = None

            def verify(self, files_modified, tests_run):
                return SimpleNamespace(
                    passed=True,
                    errors=(),
                    report=SimpleNamespace(
                        confidence=1.0,
                        status=SimpleNamespace(value="passed"),
                        to_dict=lambda: {"status": "passed"},
                    ),
                )

            def verify_task_deliverable(self, task, files_modified, skills):
                return ("deliverable quality: semantic main heading required",)

        planner = ReadPlanner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app").mkdir()
            (root / "app" / "index.html").write_text(
                "<body><div>Rosales Cafe</div></body>",
                encoding="utf-8",
            )
            initial = AgentState(
                task="repair landing page",
                selected_model="model/a",
                max_iterations=12,
                files_modified=("app/index.html",),
            )
            result = AgentLoop(
                root=tmp,
                planner=planner,
                verifier=Verifier(),
            ).run(
                task="repair landing page",
                selected_model="model/a",
                max_iterations=12,
                initial_state=initial,
            )

        self.assertEqual(result.state.status.value, "blocked")
        self.assertEqual(result.failure_kind, "technical")
        self.assertEqual(planner.calls, 3)
        self.assertIn("stalled_repeated_read", " ".join(result.state.errors))
        self.assertEqual(result.state.files_modified, ("app/index.html",))


if __name__ == "__main__":
    unittest.main()
