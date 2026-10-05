import tempfile
import unittest
from pathlib import Path

from olympus.agent.test_resolver import resolve_test_module


class TestTestResolver(unittest.TestCase):

    def test_agent_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_test_module(
                tmp,
                "olympus/agent/example.py",
            )
            self.assertEqual(
                result,
                "tests.test_safe_apply",
            )

    def test_matching_test_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / "tests"
            tests.mkdir()
            (tests / "test_example.py").write_text("")

            result = resolve_test_module(
                tmp,
                "olympus/example.py",
            )

            self.assertEqual(
                result,
                "tests.test_example",
            )

    def test_unknown_scope_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                resolve_test_module(
                    tmp,
                    "backend/unknown.py",
                )

    def test_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                resolve_test_module(
                    tmp,
                    "../evil.py",
                )


if __name__ == "__main__":
    unittest.main()
