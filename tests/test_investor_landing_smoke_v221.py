import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load_smoke_module():
    path = ROOT / "scripts" / "investor_landing_smoke.py"
    spec = importlib.util.spec_from_file_location("investor_landing_smoke", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InvestorLandingSmokeV221Tests(unittest.TestCase):
    def test_complete_investor_story_reaches_working_preview(self):
        smoke = _load_smoke_module()
        with tempfile.TemporaryDirectory() as directory:
            result = smoke.run_smoke(Path(directory))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["models_attempted"], [
                "omniroute::primary-free", "groq::investor-demo",
            ])
            self.assertTrue(all(result["checks"].values()))
            html = Path(directory, "index.html")
            archive = Path(directory, "olympus-investor-demo.zip")
            self.assertTrue(html.is_file())
            self.assertTrue(archive.is_file())
            source = html.read_text(encoding="utf-8")
            self.assertIn("Transforme ideias em", source)
            self.assertNotIn("Welcome", source)


if __name__ == "__main__":
    unittest.main()
