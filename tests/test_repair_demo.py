import unittest

from olympus.agent.repair_demo import dobro


class TestRepairDemo(unittest.TestCase):

    def test_dobro(self):
        self.assertEqual(dobro(5), 10)
        self.assertEqual(dobro(-3), -6)


if __name__ == "__main__":
    unittest.main()
