import unittest
from olympus.agent.calcular_desconto import calcular_desconto

class TestCalcularDesconto(unittest.TestCase):
    def test_calcular_desconto_basic(self):
        self.assertAlmostEqual(calcular_desconto(100, 10), 90)

    def test_calcular_desconto_zero_percent(self):
        self.assertAlmostEqual(calcular_desconto(50, 0), 50)

    def test_calcular_desconto_full_percent(self):
        self.assertAlmostEqual(calcular_desconto(200, 100), 0)

if __name__ == '__main__':
    unittest.main()
