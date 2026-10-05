import unittest

from olympus.agent.model_selector import OlympusModelSelector


class TestModelSelector(unittest.TestCase):

    def test_selector_constructs(self):
        selector = OlympusModelSelector()
        self.assertIsNotNone(selector.registry)
        self.assertIsNotNone(selector.classifier)
        self.assertIsNotNone(selector.engine)

    def test_uses_real_registry(self):
        selector = OlympusModelSelector()
        models = selector.registry.listar()

        ids = [model.id for model in models]

        self.assertIn("openrouter/openrouter/free", ids)

    def test_interface_request_is_classified_as_code(self):
        selector = OlympusModelSelector()

        task = selector._build_task("faça uma interface com cara do google")

        self.assertEqual(task.tipo.value, "codigo")
        self.assertEqual(
            selector.select_candidates(task.descricao),
            ("openrouter/openrouter/free",),
        )

    def test_landing_page_with_manual_comparison_selects_code_route(self):
        selector = OlympusModelSelector()
        description = (
            "Crie uma landing page profissional com comparação entre trabalho manual e Olympus"
        )
        task = selector._build_task(description)
        self.assertEqual(task.tipo.value, "codigo")
        self.assertEqual(
            selector.select_candidates(description),
            ("openrouter/openrouter/free",),
        )

    def test_legitimate_documentation_task_has_a_free_route(self):
        selector = OlympusModelSelector()
        description = "Escreva um manual e um guia de uso para o produto"
        task = selector._build_task(description)
        self.assertEqual(task.tipo.value, "documentacao")
        self.assertEqual(
            selector.select_candidates(description),
            ("openrouter/openrouter/free",),
        )


if __name__ == "__main__":
    unittest.main()
