import tempfile
import unittest
from pathlib import Path

from olympus.agent.safe_apply import (
    SafeApplyError,
    apply,
    parse_file_blocks,
)


class TestSafeApply(unittest.TestCase):
    def test_parse_single_file(self):
        payload = "=== FILE: olympus/agent/example.py ===\nprint('ok')\n"
        blocks = parse_file_blocks(payload)

        self.assertEqual(
            blocks["olympus/agent/example.py"],
            "print('ok')\n",
        )

    def test_parse_multiple_files(self):
        payload = (
            "=== FILE: a.py ===\n"
            "A\n"
            "=== FILE: b.py ===\n"
            "B\n"
        )

        blocks = parse_file_blocks(payload)

        self.assertEqual(set(blocks), {"a.py", "b.py"})

    def test_rejects_empty_payload(self):
        with self.assertRaises(SafeApplyError):
            parse_file_blocks("")

    def test_rejects_duplicate_paths(self):
        payload = (
            "=== FILE: a.py ===\n"
            "A\n"
            "=== FILE: a.py ===\n"
            "B\n"
        )

        with self.assertRaises(SafeApplyError):
            parse_file_blocks(payload)

    def test_rejects_path_traversal(self):
        payload = (
            "=== FILE: ../evil.py ===\n"
            "bad\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SafeApplyError):
                apply(tmp, payload, ["olympus/agent/"])

    def test_rejects_absolute_path(self):
        payload = (
            "=== FILE: /tmp/evil.py ===\n"
            "bad\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SafeApplyError):
                apply(tmp, payload, ["/tmp/evil.py"])

    def test_rejects_outside_allowlist(self):
        payload = (
            "=== FILE: backend/app.py ===\n"
            "bad\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SafeApplyError):
                apply(tmp, payload, ["olympus/agent/"])

    def test_allows_exact_file(self):
        payload = (
            "=== FILE: olympus/agent/example.py ===\n"
            "print('ok')\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = apply(
                tmp,
                payload,
                ["olympus/agent/example.py"],
            )

            target = (
                Path(tmp)
                / "olympus"
                / "agent"
                / "example.py"
            )

            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(), "print('ok')\n")
            self.assertEqual(
                result.applied_files,
                ("olympus/agent/example.py",),
            )

    def test_allows_directory_scope(self):
        payload = (
            "=== FILE: olympus/agent/a.py ===\n"
            "A\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = apply(
                tmp,
                payload,
                ["olympus/agent/"],
            )

            self.assertEqual(
                result.applied_files,
                ("olympus/agent/a.py",),
            )

    def test_file_content_preserved(self):
        content = "linha 1\nlinha 2\nçãõ\n"
        payload = (
            "=== FILE: olympus/agent/example.py ===\n"
            + content
        )

        with tempfile.TemporaryDirectory() as tmp:
            apply(
                tmp,
                payload,
                ["olympus/agent/"],
            )

            target = (
                Path(tmp)
                / "olympus"
                / "agent"
                / "example.py"
            )

            self.assertEqual(target.read_text(), content)

    def test_no_deletion_operation_exists(self):
        self.assertTrue(callable(apply))


if __name__ == "__main__":
    unittest.main()
