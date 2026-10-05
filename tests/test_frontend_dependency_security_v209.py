import json
import unittest
from pathlib import Path


class FrontendDependencySecurityV209Tests(unittest.TestCase):
    def test_next_is_pinned_to_current_maintenance_lts_security_release(self):
        package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["dependencies"]["next"], "16.3.5")
        self.assertEqual(package["dependencies"]["react"], "18.3.1")
        self.assertEqual(package["dependencies"]["react-dom"], "18.3.1")
        self.assertFalse(package["dependencies"]["next"].startswith(("^", "~")))


if __name__ == "__main__":
    unittest.main()
