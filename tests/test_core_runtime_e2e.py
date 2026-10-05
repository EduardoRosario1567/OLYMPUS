import unittest

from scripts.core_runtime_e2e import run


class TestCoreRuntimeEndToEnd(unittest.TestCase):
    """Release gate that crosses transport, runtime and delivery boundaries."""

    def test_complete_mission_crosses_the_core_and_delivers_result(self):
        result = run()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["models_attempted"], ["primary/free", "fallback/free"])


if __name__ == "__main__":
    unittest.main()
