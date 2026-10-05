import unittest

from olympus.agent.multibrain_registry import (
    FREE_ROUTER_MODEL_ID,
    build_multibrain_registry,
)
from olympus.agent.model_selector import OlympusModelSelector
from olympus.models import TaskType


class TestMultiBrainRegistry(unittest.TestCase):
    def test_uses_stable_free_models_router(self):
        registry = build_multibrain_registry()
        ids = {model.id for model in registry.listar()}
        self.assertEqual(ids, {"openrouter/openrouter/free"})

    def test_free_router_supports_autonomous_code_tasks(self):
        registry = build_multibrain_registry()
        model = registry.obter(FREE_ROUTER_MODEL_ID)
        self.assertTrue(model.suporta(TaskType.CODIGO))
        self.assertTrue(model.suporta(TaskType.TESTES))
        self.assertEqual(model.custo_estimado, 0.0)

    def test_observed_evidence_is_recorded(self):
        registry = build_multibrain_registry()
        registry.registrar_resultado_observado(
            FREE_ROUTER_MODEL_ID, success=True, latency_ms=1000
        )
        model = registry.obter(FREE_ROUTER_MODEL_ID)
        self.assertEqual(model.observed_attempts, 1)
        self.assertEqual(model.observed_successes, 1)

    def test_selector_chooses_free_router(self):
        candidates = OlympusModelSelector().select_candidates(
            "Crie uma funcao Python para validar email"
        )
        self.assertEqual(candidates, (FREE_ROUTER_MODEL_ID,))


if __name__ == "__main__":
    unittest.main()
