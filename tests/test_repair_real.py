import unittest

from olympus.agent.repair_real import normalizar_nome


class TestNormalizarNome(unittest.TestCase):

    def test_remove_espacos_e_capitaliza(self):
        self.assertEqual(
            normalizar_nome("  fernando   fernandes  "),
            "Fernando Fernandes",
        )

    def test_multiplos_espacos(self):
        self.assertEqual(
            normalizar_nome("maria     silva"),
            "Maria Silva",
        )


if __name__ == "__main__":
    unittest.main()
