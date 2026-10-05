import tempfile
import unittest
from pathlib import Path

from olympus.agent.safe_edit import SafeEditError, apply_edit


class TestSafeEdit(unittest.TestCase):

    def test_exact_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "olympus/agent/a.py"
            target.parent.mkdir(parents=True)
            target.write_text("A = 1\n", encoding="utf-8")

            result = apply_edit(
                tmp,
                "olympus/agent/a.py",
                "A = 1",
                "A = 2",
                ["olympus/agent/"],
            )

            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "A = 2\n",
            )
            self.assertEqual(result.replacements, 1)

    def test_blocks_outside_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "backend/a.py"
            target.parent.mkdir(parents=True)
            target.write_text("A = 1\n")

            with self.assertRaises(Exception):
                apply_edit(
                    tmp,
                    "backend/a.py",
                    "A = 1",
                    "A = 2",
                    ["olympus/agent/"],
                )

    def test_rejects_missing_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "olympus/agent/a.py"
            target.parent.mkdir(parents=True)
            target.write_text("A = 1\n")

            with self.assertRaises(SafeEditError):
                apply_edit(
                    tmp,
                    "olympus/agent/a.py",
                    "NOT HERE",
                    "A = 2",
                    ["olympus/agent/"],
                )

    def test_rejects_ambiguous_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "olympus/agent/a.py"
            target.parent.mkdir(parents=True)
            target.write_text("X\nX\n")

            with self.assertRaises(SafeEditError):
                apply_edit(
                    tmp,
                    "olympus/agent/a.py",
                    "X",
                    "Y",
                    ["olympus/agent/"],
                )


if __name__ == "__main__":
    unittest.main()
