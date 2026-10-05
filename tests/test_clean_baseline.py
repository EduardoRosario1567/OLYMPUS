import unittest
from pathlib import Path

from olympus.agent.model_selector import OlympusModelSelector


class TestCleanBaseline(unittest.TestCase):
    def test_dev_launcher_has_no_old_downloads_checkout(self):
        text = Path("scripts/olympus_dev.sh").read_text(encoding="utf-8")
        self.assertNotIn("Downloads/olympus-repo", text)
        self.assertIn('SCRIPT_DIR=', text)

    def test_source_of_truth_exists(self):
        self.assertTrue(Path("docs/OLYMPUS-SOURCE-OF-TRUTH.md").is_file())

    def test_selector_exposes_ordered_candidates(self):
        selector = OlympusModelSelector()
        candidates = selector.select_candidates("Crie uma função Python chamada exemplo")
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0], selector.select("Crie uma função Python chamada exemplo"))


if __name__ == "__main__":
    unittest.main()
