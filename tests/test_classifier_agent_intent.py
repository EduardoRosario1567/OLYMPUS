import unittest

from olympus.classifier import TaskClassifier
from olympus.models import TaskType


class TestClassifierAgentIntent(unittest.TestCase):

    def setUp(self):
        self.classifier = TaskClassifier()

    def test_create_constant_is_code(self):
        self.assertEqual(
            self.classifier.classify(
                "Crie uma constante chamada PROJECT_MODE"
            ),
            TaskType.CODIGO,
        )

    def test_add_function_is_code(self):
        self.assertEqual(
            self.classifier.classify(
                "Adicione uma função para calcular a média"
            ),
            TaskType.CODIGO,
        )

    def test_implement_module_is_code(self):
        self.assertEqual(
            self.classifier.classify(
                "Implemente um módulo para validação"
            ),
            TaskType.CODIGO,
        )

    def test_fix_file_is_code(self):
        self.assertEqual(
            self.classifier.classify(
                "Corrija este arquivo para tratar valores vazios"
            ),
            TaskType.CODIGO,
        )

    def test_architecture_remains_architecture(self):
        self.assertEqual(
            self.classifier.classify(
                "Analise a arquitetura do sistema"
            ),
            TaskType.ARQUITETURA,
        )

    def test_professional_landing_page_wins_over_ambiguous_manual_word(self):
        task = (
            "Crie uma landing page profissional e responsiva para o Olympus. "
            "Inclua uma comparação visual entre trabalho manual e trabalho com Olympus. "
            "Revise integralmente o resultado antes de concluir."
        )
        self.assertEqual(self.classifier.classify(task), TaskType.CODIGO)

    def test_actual_olympus_skill_mission_is_code(self):
        task = (
            "Crie uma landing page profissional e responsiva para o Olympus, apresentado "
            "como uma plataforma autônoma de criação de software. Use identidade visual "
            "premium, seis benefícios, comparação entre trabalho manual e trabalho com "
            "Olympus, depoimento, chamada final e rodapé completo."
        )
        self.assertEqual(self.classifier.classify(task), TaskType.CODIGO)

    def test_real_user_manual_remains_documentation(self):
        self.assertEqual(
            self.classifier.classify("Escreva um manual e um guia de uso para o produto"),
            TaskType.DOCUMENTACAO,
        )


if __name__ == "__main__":
    unittest.main()
