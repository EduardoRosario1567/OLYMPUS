"""Proof that optional remote Python tests never downgrade Docker isolation.

No E2B network/API calls are performed by these tests.
"""
import io
import os
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from olympus.agent.test_runner import TargetedTestRunner
from scripts.remote_e2b_unittest_runner import execute, build_python_bundle


class E2BTestRunnerConsolidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (self.root / "tests" / "test_smoke.py").write_text(
            "import unittest\nclass Tests(unittest.TestCase):\n"
            "    def test_success(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )

    def test_default_keeps_local_container(self):
        completed = subprocess.CompletedProcess(
            ["docker"], 0, "",
            "Ran 1 test in 0.000s\n\nOK\n",
        )
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "docker"}):
            with patch("olympus.agent.test_runner.ContainerExecutor") as docker:
                docker.return_value.run.return_value = completed
                with patch("scripts.remote_e2b_unittest_runner.execute") as remote:
                    result = TargetedTestRunner(str(self.root)).run_unittest(["tests.test_smoke"])
        self.assertTrue(result.success)
        docker.return_value.run.assert_called_once()
        remote.assert_not_called()

    def test_e2b_explicit_routes_without_calling_docker(self):
        result_data = {
            "status": "DONE", "exit_code": 0, "stdout": "",
            "stderr": "Ran 1 test in 0.001s\nOK\n"
        }
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "e2b"}):
            with patch("olympus.agent.test_runner.ContainerExecutor") as docker:
                with patch("scripts.remote_e2b_unittest_runner.execute", return_value=result_data) as remote:
                    result = TargetedTestRunner(str(self.root)).run_unittest(["tests.test_smoke"])
        self.assertTrue(result.success)
        self.assertEqual(result.command[0], "e2b")
        remote.assert_called_once_with(str(self.root.resolve()), "tests.test_smoke", timeout=60)
        docker.assert_not_called()

    def test_unknown_provider_and_remote_multiple_modules_fail_closed(self):
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "host"}):
            with patch("olympus.agent.test_runner.ContainerExecutor") as docker:
                with self.assertRaisesRegex(ValueError, "BLOCKED"):
                    TargetedTestRunner(str(self.root)).run_unittest(["tests.test_smoke"])
                docker.assert_not_called()
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "e2b"}):
            with patch("scripts.remote_e2b_unittest_runner.execute") as remote:
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    TargetedTestRunner(str(self.root)).run_unittest(["tests.test_smoke", "tests.test_other"])
                with self.assertRaisesRegex(ValueError, "shell checks"):
                    TargetedTestRunner(str(self.root)).run_unittest(["shell:scripts/check.sh"])
                remote.assert_not_called()

    def test_remote_failure_never_falls_back_to_host_or_docker(self):
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "e2b"}):
            with patch("olympus.agent.test_runner.ContainerExecutor") as docker:
                with patch("scripts.remote_e2b_unittest_runner.execute", side_effect=PermissionError("BLOCKED: no authorization")):
                    with self.assertRaisesRegex(PermissionError, "BLOCKED"):
                        TargetedTestRunner(str(self.root)).run_unittest(["tests.test_smoke"])
                docker.assert_not_called()

    def test_live_remote_is_never_called_without_explicit_authorization(self):
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "e2b", "OLYMPUS_REMOTE_SANDBOX_AUTHORIZED": "0", "E2B_API_KEY": "fake-test-value"}):
            with patch("olympus.agent.test_runner.ContainerExecutor") as docker:
                with self.assertRaisesRegex(PermissionError, "BLOCKED"):
                    TargetedTestRunner(str(self.root)).run_unittest(["tests.test_smoke"])
                docker.assert_not_called()

    def test_bundle_excludes_credentials_named_files(self):
        (self.root / "tests" / ".env").write_text("PRIVATE_VALUE", encoding="utf-8")
        (self.root / "tests" / "api_key.py").write_text("PRIVATE_VALUE", encoding="utf-8")
        data = build_python_bundle(self.root)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIn("tests/test_smoke.py", archive.namelist())
            self.assertNotIn("tests/.env", archive.namelist())
            self.assertNotIn("tests/api_key.py", archive.namelist())

    def test_remote_all_tests_skipped_does_not_pass(self):
        class FakeSandbox:
            destroyed = False
            files = types.SimpleNamespace(write=lambda *_: None)
            commands = types.SimpleNamespace(run=lambda *_args, **_kwargs: types.SimpleNamespace(
                stdout="", stderr="Ran 1 test in 0.01s\n\nOK (skipped=1)\n", exit_code=0,
            ))
            @classmethod
            def create(cls, **kwargs):
                return cls()
            def kill(self):
                type(self).destroyed = True

        with patch.dict(sys.modules, {"e2b": types.SimpleNamespace(Sandbox=FakeSandbox)}):
            result = execute(self.root, "tests.test_smoke", environ={
                "OLYMPUS_REMOTE_SANDBOX_AUTHORIZED": "1", "E2B_API_KEY": "fake-test-value",
            })
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(FakeSandbox.destroyed)


if __name__ == "__main__":
    unittest.main()
