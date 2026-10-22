"""Contract regression without live providers or macOS."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "app" / "api" / "missions.py"


class MissionContractTests(unittest.TestCase):
    def test_static_prompt_contains_real_newlines(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        mission_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_mission")
        text_literals = [n.value for n in ast.walk(mission_fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertTrue(any("site/index.html" in value and value.endswith("\n") for value in text_literals))
        self.assertTrue(any("\n\n" in value and "OLYMPUS delivery gate" in value for value in text_literals))
        self.assertFalse(any("\\n" in value and "site/index.html" in value for value in text_literals))

    def test_validation_cannot_be_skipped_when_delivery_requested(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if static_delivery and result.success:", source)
        self.assertIn("preserve_validated_site(workspace, delivery_root, mission_id)", source)
        self.assertIn('rec["status"] = "failed" if delivery_error', source)


if __name__ == "__main__":
    unittest.main()
