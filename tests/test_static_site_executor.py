"""Fail-closed tests for model-authored, static-only files."""
import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.static_site_executor import StaticSiteActionExecutor, static_site_loop_factory
from unittest.mock import patch


class StaticSiteActionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.writer = StaticSiteActionExecutor(str(self.root))

    def action(self, kind, target=None, payload=None):
        return self.writer.execute(AgentAction(kind, target=target, payload=payload))

    def test_writes_site_and_can_read_it(self):
        result = self.action(ActionType.CREATE_FILE, "site/index.html", "<h1>Rosales Cafe</h1>")
        self.assertTrue(result.success, result.error)
        self.assertEqual((self.root / "site/index.html").read_text().strip(), "<h1>Rosales Cafe</h1>")
        result = self.action(ActionType.READ_FILE, "site/index.html")
        self.assertTrue(result.success, result.error)

    def test_can_patch_existing_site_text(self):
        self.assertTrue(self.action(ActionType.CREATE_FILE, "site/style.css", "h1 { color: red; }").success)
        result = self.action(ActionType.PATCH_FILE, "site/style.css", {
            "operation": "replace_text",
            "old_text": "red",
            "new_content": "green",
        })
        self.assertTrue(result.success, result.error)
        self.assertIn("green", (self.root / "site/style.css").read_text())

    def test_denies_process_and_research_actions_without_delegation(self):
        for kind in (ActionType.RUN_TEST, ActionType.RESEARCH_SOURCES, ActionType.IMPORT_ASSET, ActionType.SEARCH_CODE):
            result = self.action(kind, "tests.test_model")
            self.assertFalse(result.success, kind)
            self.assertIn("BLOCKED", result.error)
        self.assertFalse((self.root / "tests").exists())

    def test_denies_writing_outside_site_and_private_files(self):
        targets = [
            "backend/app/main.py", "../site/index.html",
            "site/../../.env", "site/.env", "site/token.py",
            "site/secrets.pem", "site//index.html", "site/./index.html",
            "site/secret/file.py", "/tmp/index.html",
            "site\\index.html", "site/node_modules/a.js",
        ]
        for target in targets:
            with self.subTest(target=target):
                result = self.action(ActionType.CREATE_FILE, target, "unsafe")
                self.assertFalse(result.success, target)
        self.assertFalse((self.root / "site").exists())
        self.assertFalse((self.root / "backend").exists())

    def test_denies_symlink_into_external_location(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "site").symlink_to(outside, target_is_directory=True)
            result = self.action(ActionType.CREATE_FILE, "site/index.html", "unsafe")
            self.assertFalse(result.success)
            self.assertFalse((Path(outside) / "index.html").exists())

    def test_denies_existing_symlink_file(self):
        (self.root / "site").mkdir()
        with tempfile.NamedTemporaryFile() as f:
            (self.root / "site/index.html").symlink_to(f.name)
            result = self.action(ActionType.CREATE_FILE, "site/index.html", "unsafe")
            self.assertFalse(result.success)

    def test_denies_oversized_assets_and_patch_payloads(self):
        self.assertFalse(self.action(ActionType.CREATE_FILE, "site/huge.css", "x" * (512 * 1024 + 1)).success)
        self.assertFalse(self.action(ActionType.PATCH_FILE, "site/index.html", {
            "operation": "append_block", "new_content": "x" * (512 * 1024 + 1),
        }).success)

    def test_model_loop_factory_cannot_execute_generated_tests(self):
        verifier = object()
        loop = static_site_loop_factory(lambda root: verifier)(str(self.root), object())
        self.assertIsInstance(loop.executor, StaticSiteActionExecutor)
        self.assertIs(loop.verifier, verifier)
        with patch.object(loop.executor.test_runner, "run_unittest",
                          side_effect=AssertionError("model code executed")) as unsafe:
            action = AgentAction(ActionType.RUN_TEST, target="tests.test_generated",
                                 payload=["tests.test_generated"])
            response = loop.executor.execute(action)
        self.assertFalse(response.success)
        self.assertIn("BLOCKED", response.error)
        unsafe.assert_not_called()

    def test_finish_does_not_mean_site_was_validated(self):
        result = self.action(ActionType.FINISH, payload="Site complete")
        self.assertTrue(result.success)
        self.assertFalse((self.root / "site/index.html").exists())


if __name__ == "__main__":
    unittest.main()
