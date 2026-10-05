import tempfile
import unittest
from pathlib import Path

from olympus.agent.loop import AgentLoop


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


if __name__ == "__main__":
    unittest.main()
