import tempfile
import unittest
from unittest.mock import Mock
from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.agent.loop import AgentLoop


class CloudAgentIsolationWiringTests(unittest.TestCase):
    def test_isolated_mode_reaches_action_executor(self):
        with tempfile.TemporaryDirectory() as workspace:
            agent = AutonomousDeveloper(workspace, router=Mock(), isolated_tests=True)
            loop = agent.runner.loop_factory(workspace, Mock())
            self.assertIsInstance(loop, AgentLoop)
            self.assertTrue(loop.executor.test_runner.isolated)

    def test_default_mode_preserves_legacy_internal_tests(self):
        with tempfile.TemporaryDirectory() as workspace:
            agent = AutonomousDeveloper(workspace, router=Mock())
            loop = agent.runner.loop_factory(workspace, Mock())
            self.assertFalse(loop.executor.test_runner.isolated)


if __name__ == "__main__":
    unittest.main()
