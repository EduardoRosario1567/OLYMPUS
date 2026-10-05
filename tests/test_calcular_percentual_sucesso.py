import unittest

from olympus.agent.calcular_percentual_sucesso import calcular_percentual_sucesso

class TestCalcularPercentualSucesso(unittest.TestCase):
    def test_total_zero(self):
        self.assertEqual(calcular_percentual_sucesso(0, 0), 0)

    def test_full_success(self):
        self.assertEqual(calcular_percentual_sucesso(5, 5), 100)

    def test_no_success(self):
        self.assertEqual(calcular_percentual_sucesso(7, 0), 0)

    def test_partial_success(self):
        self.assertEqual(calcular_percentual_sucesso(10, 3), 30)

if __name__ == '__main__':
    unittest.main()
