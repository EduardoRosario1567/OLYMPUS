import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.agent.test_runner import TargetedTestRunner


class IsolatedTestRunnerIntegration(unittest.TestCase):
    def test_calls_isolated_executor_in_opt_in_mode(self):
        with tempfile.TemporaryDirectory() as work:
            with patch("scripts.isolated_unittest_runner.execute", return_value={
                "status": "DONE", "exit_code": 0, "stdout": "", "stderr": "Ran 1 test in 0.001s\nOK"
            }) as isolated:
                result = TargetedTestRunner(work, isolated=True).run_unittest(["tests.test_example"])
            self.assertTrue(result.success)
            isolated.assert_called_once_with(str(Path(work).resolve()), "tests.test_example", timeout=60)

    def test_multiple_modules_fail_closed_without_running(self):
        with tempfile.TemporaryDirectory() as work:
            with patch("scripts.isolated_unittest_runner.execute") as isolated:
                with self.assertRaises(ValueError):
                    TargetedTestRunner(work, isolated=True).run_unittest(["tests.a", "tests.b"])
                isolated.assert_not_called()

    def test_docker_unavailable_never_falls_back_to_host(self):
        with tempfile.TemporaryDirectory() as work:
            with patch("scripts.isolated_unittest_runner.execute", side_effect=RuntimeError("BLOCKED: Docker unavailable")):
                with self.assertRaisesRegex(RuntimeError, "BLOCKED"):
                    TargetedTestRunner(work, isolated=True).run_unittest(["tests.example"])


if __name__ == "__main__":
    unittest.main()
