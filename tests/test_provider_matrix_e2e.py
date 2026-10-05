import unittest

from scripts.provider_matrix_e2e import run


class TestProviderMatrixEndToEnd(unittest.TestCase):
    def test_large_mission_uses_independent_free_sources_and_delivers(self):
        result = run()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(len(result["registered_sources"]), 10)


if __name__ == "__main__":
    unittest.main()
