import json
import unittest
from pathlib import Path


class FrontendDependencySecurityV209Tests(unittest.TestCase):
    def test_next_is_pinned_above_known_security_floor(self):
        package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))
        version = package["dependencies"]["next"]
        self.assertRegex(version, r"^16\.\d+\.\d+$")
        # Current advisory floor, including GHSA-cjq9-62q9-8jv4.
        self.assertGreaterEqual(tuple(map(int, version.split("."))), (16, 3, 8))
        lock = json.loads(Path("frontend/package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"]["node_modules/next"]["version"], version)
        self.assertEqual(package["dependencies"]["react"], "18.3.1")
        self.assertEqual(package["dependencies"]["react-dom"], "18.3.1")
        self.assertFalse(package["dependencies"]["next"].startswith(("^", "~")))


if __name__ == "__main__":
    unittest.main()
