import io
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from olympus.agent.test_runner import TargetedTestRunner
from scripts.remote_e2b_unittest_runner import build_python_bundle, execute


class FakeCommands:
    def __init__(self):
        self.calls = []

    def run(self, command, timeout):
        self.calls.append((command, timeout))
        return types.SimpleNamespace(
            exit_code=0,
            stdout="",
            stderr="test_ok (tests.test_sample.Sample.test_ok) ... ok\n\nRan 1 test in 0.000s\n\nOK\n",
        )


class FakeSandbox:
    created = []

    def __init__(self):
        self.uploads = []
        self.files = types.SimpleNamespace(write=lambda name, data: self.uploads.append((name, data)))
        self.commands = FakeCommands()
        self.sandbox_id = "test-sandbox-only"
        self.killed = False

    @classmethod
    def create(cls, **kwargs):
        obj = cls()
        obj.kwargs = kwargs
        cls.created.append(obj)
        return obj

    def kill(self):
        self.killed = True


class E2BRemoteRunnerTests(unittest.TestCase):
    def setUp(self):
        FakeSandbox.created.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "__init__.py").write_text("")
        (self.root / "tests" / "test_sample.py").write_text(
            "import unittest\nclass Sample(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n"
        )
        (self.root / "tests" / ".env").write_text("SUPERSECRET=must-not-upload")
        (self.root / "tests" / "token.py").write_text("SUPERSECRET='must-not-upload'")

    def test_missing_authorization_and_key_never_create_remote_sandbox(self):
        with self.assertRaisesRegex(PermissionError, "not authorized"):
            execute(self.root, "tests.test_sample", environ={"E2B_API_KEY": "fake"})
        with self.assertRaisesRegex(RuntimeError, "E2B_API_KEY"):
            execute(self.root, "tests.test_sample", environ={"OLYMPUS_REMOTE_SANDBOX_AUTHORIZED": "1"})
        self.assertEqual(FakeSandbox.created, [])

    def test_invalid_module_is_rejected_before_billing(self):
        with self.assertRaisesRegex(ValueError, "invalid"):
            execute(self.root, "tests.test_sample;rm -rf /", environ={
                "OLYMPUS_REMOTE_SANDBOX_AUTHORIZED": "1", "E2B_API_KEY": "fake"
            })

    def test_real_sdk_boundary_with_mock_and_sandbox_cleanup(self):
        fake_module = types.SimpleNamespace(Sandbox=FakeSandbox)
        with patch.dict(sys.modules, {"e2b": fake_module}):
            result = execute(self.root, "tests.test_sample", timeout=40, environ={
                "OLYMPUS_REMOTE_SANDBOX_AUTHORIZED": "1", "E2B_API_KEY": "fake"
            })
        self.assertEqual(result["status"], "DONE")
        sandbox = FakeSandbox.created[0]
        self.assertTrue(sandbox.killed)
        self.assertEqual(sandbox.kwargs["allow_internet_access"], False)
        self.assertEqual(sandbox.kwargs["envs"], {})
        self.assertEqual(sandbox.kwargs["timeout"], 60)
        self.assertEqual(len(sandbox.uploads), 1)
        with zipfile.ZipFile(io.BytesIO(sandbox.uploads[0][1])) as archive:
            self.assertIn("tests/test_sample.py", archive.namelist())
            self.assertNotIn("tests/.env", archive.namelist())
            self.assertNotIn("tests/token.py", archive.namelist())
        self.assertNotIn("fake", sandbox.commands.calls[0][0])

    def test_symlink_to_outside_file_is_rejected(self):
        target = self.root / "outside.py"
        target.write_text("password=123")
        (self.root / "tests" / "linked.py").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            build_python_bundle(self.root)

    def test_test_runner_selects_e2b_without_using_host_or_docker(self):
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "e2b"}):
            with patch("scripts.remote_e2b_unittest_runner.execute", return_value={
                "status": "DONE", "exit_code": 0, "stdout": "", "stderr": "Ran 1 test in 0.01s\nOK"
            }) as call, patch("scripts.isolated_unittest_runner.execute") as docker:
                result = TargetedTestRunner(str(self.root), isolated=True).run_unittest(["tests.test_sample"])
        self.assertTrue(result.success)
        call.assert_called_once()
        docker.assert_not_called()

    def test_unsupported_provider_fails_closed(self):
        with patch.dict(os.environ, {"OLYMPUS_ISOLATED_TEST_PROVIDER": "host"}):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                TargetedTestRunner(str(self.root), isolated=True).run_unittest(["tests.test_sample"])


if __name__ == "__main__":
    unittest.main()
