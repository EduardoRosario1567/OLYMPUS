import unittest

from olympus.agent.architecture_micro import PROJECT_ISOLATION_STRATEGY


class TestArchitectureMicro(unittest.TestCase):

    def test_project_isolation_strategy(self):
        self.assertEqual(
            PROJECT_ISOLATION_STRATEGY,
            "context-per-project",
        )


if __name__ == "__main__":
    unittest.main()
