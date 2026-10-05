import unittest

from olympus.agent.mvp_media import calcular_media


class TestCalcularMedia(unittest.TestCase):

    def test_media(self):
        self.assertEqual(
            calcular_media([10, 20, 30]),
            20,
        )

    def test_media_decimal(self):
        self.assertAlmostEqual(
            calcular_media([1, 2, 2]),
            5 / 3,
        )


if __name__ == "__main__":
    unittest.main()
