import unittest

from olympus.agent.test_runner import TargetedTestRunner


class TestTargetedTestRunner(unittest.TestCase):

    def setUp(self):
        self.runner = TargetedTestRunner()

    def test_runs_allowed_test(self):
        result = self.runner.run_unittest(
            ["tests.test_safe_apply"]
        )

        self.assertTrue(result.success)
        self.assertEqual(result.returncode, 0)

    def test_multiple_test_modules(self):
        result = self.runner.run_unittest(
            [
                "tests.test_safe_apply",
                "tests.test_dev_agent",
            ]
        )

        self.assertTrue(result.success)

    def test_rejects_empty_tests(self):
        with self.assertRaises(ValueError):
            self.runner.run_unittest([])

    def test_rejects_non_test_module(self):
        with self.assertRaises(ValueError):
            self.runner.run_unittest(
                ["olympus.models"]
            )

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            self.runner.run_unittest(
                ["tests...evil"]
            )

    def test_rejects_shell_characters(self):
        for bad in (
            "tests.foo;rm",
            "tests.foo|cat",
            "tests.foo&bad",
            "tests/foo",
        ):
            with self.assertRaises(ValueError):
                self.runner.run_unittest([bad])

    def test_command_is_not_shell(self):
        result = self.runner.run_unittest(
            ["tests.test_safe_apply"]
        )

        self.assertEqual(result.command[1:3], ("-m", "unittest"))
        from pathlib import Path
        self.assertTrue(Path(result.command[0]).is_absolute())
        self.assertTrue(Path(result.command[0]).is_file())


if __name__ == "__main__":
    unittest.main()

    def test_workspace_pythonpath_isolation(self):
        import os
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as hostile:
            root = Path(workspace)
            bad = Path(hostile)

            (root / "olympus").mkdir()
            (root / "tests").mkdir()
            (root / "olympus/__init__.py").write_text("")
            (root / "tests/__init__.py").write_text("")
            (root / "olympus/identity.py").write_text('VALUE = "workspace"\n')
            (bad / "olympus").mkdir()
            (bad / "olympus/__init__.py").write_text("")
            (bad / "olympus/identity.py").write_text('VALUE = "hostile"\n')
            (root / "tests/test_identity.py").write_text(
                "from olympus.identity import VALUE\n"
                "\ndef test_identity():\n"
                "    assert VALUE == 'workspace'\n"
            )

            old_pythonpath = os.environ.get("PYTHONPATH")
            os.environ["PYTHONPATH"] = str(bad)
            try:
                result = TargetedTestRunner(str(root)).run_unittest(
                    ["tests.test_identity"]
                )
            finally:
                if old_pythonpath is None:
                    os.environ.pop("PYTHONPATH", None)
                else:
                    os.environ["PYTHONPATH"] = old_pythonpath

            self.assertTrue(result.success, result.stderr or result.stdout)
