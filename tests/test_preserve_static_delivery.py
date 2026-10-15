"""Preservation tests require no external services."""
import tempfile
import unittest
from pathlib import Path

from scripts.preserve_static_delivery import preserve_validated_site


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.site = self.base / "workspace" / "site"
        self.site.mkdir(parents=True)
        self.dest = self.base / "deliveries"

    def test_valid_site_is_preserved(self):
        (self.site / "index.html").write_text("<h1>Rosales Café</h1>", encoding="utf-8")
        receipt = preserve_validated_site(self.site.parent, self.dest, "mission123")
        self.assertEqual(receipt["status"], "DONE")
        self.assertEqual((self.dest / "mission123" / "site" / "index.html").read_text(), "<h1>Rosales Café</h1>")

    def test_blocked_site_not_preserved(self):
        (self.site / "index.html").write_text('<iframe src="x"></iframe>')
        with self.assertRaises(ValueError):
            preserve_validated_site(self.site.parent, self.dest, "mission123")
        self.assertFalse((self.dest / "mission123").exists())

    def test_no_overwrite(self):
        (self.site / "index.html").write_text("ok")
        preserve_validated_site(self.site.parent, self.dest, "mission123")
        with self.assertRaises(FileExistsError):
            preserve_validated_site(self.site.parent, self.dest, "mission123")

    def test_no_traversal_id(self):
        (self.site / "index.html").write_text("ok")
        with self.assertRaises(ValueError):
            preserve_validated_site(self.site.parent, self.dest, "../wrong")


if __name__ == "__main__":
    unittest.main()
