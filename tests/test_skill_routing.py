import unittest

from olympus.agent.multibrain_registry import build_multibrain_registry
from olympus.routing.model_lab import BenchmarkCategory, ModelLab
from olympus.skills import SkillRegistry, SkillResolver, SkillRoutePlanner
from olympus.models import Modelo, TaskType
from olympus.registry import ModelRegistry


def comparative_registry():
    registry = ModelRegistry()
    registry.registrar(Modelo(
        id="model/strong", nome="Strong", provedor="test",
        capacidades=[TaskType.CODIGO], custo_estimado=0.0,
        latencia_estimada=1.0, confiabilidade=0.9,
        coding_strength=0.95, agentic_strength=0.95,
        tool_use_strength=0.95, structured_output_strength=0.95,
    ))
    registry.registrar(Modelo(
        id="model/basic", nome="Basic", provedor="test",
        capacidades=[TaskType.CODIGO], custo_estimado=0.0,
        latencia_estimada=1.0, confiabilidade=0.8,
        coding_strength=0.55, agentic_strength=0.55,
        tool_use_strength=0.55, structured_output_strength=0.55,
    ))
    return registry


class TestSkillRouting(unittest.TestCase):
    def test_skill_x_model_x_provider_is_ranked(self):
        registry = build_multibrain_registry()
        lab = ModelLab()
        routes = SkillRoutePlanner(registry, lab).rank(
            SkillResolver(SkillRegistry()).resolve("implementar codigo"),
            task_type=TaskType.CODIGO,
        )
        self.assertTrue(routes)
        self.assertTrue(all(r.provider for r in routes))
        self.assertTrue(all(r.model for r in routes))
        self.assertGreaterEqual(routes[0].final_score, routes[-1].final_score)

    def test_skill_fit_changes_with_capability(self):
        registry = comparative_registry()
        lab = ModelLab()
        coding = SkillResolver(SkillRegistry()).resolve("implementar codigo")
        routes = SkillRoutePlanner(registry, lab).rank(coding, task_type=TaskType.CODIGO)
        strong = next(r for r in routes if r.model == "model/strong")
        basic = next(r for r in routes if r.model == "model/basic")
        self.assertGreater(strong.skill_score, basic.skill_score)

    def test_observed_evidence_influences_routing(self):
        registry = comparative_registry()
        lab = ModelLab()
        for _ in range(10):
            lab.record(BenchmarkCategory.CODE_GENERATION, "test", "model/basic", success=False, timeout=True, action_compliant=False)
            lab.record(BenchmarkCategory.CODE_GENERATION, "test", "model/strong", success=True, action_compliant=True)
        skills = SkillResolver(SkillRegistry()).resolve("implementar codigo")
        routes = SkillRoutePlanner(registry, lab).rank(skills, task_type=TaskType.CODIGO)
        strong = next(r for r in routes if r.model == "model/strong")
        basic = next(r for r in routes if r.model == "model/basic")
        self.assertGreater(strong.observed_score, basic.observed_score)
        self.assertGreater(strong.final_score, basic.final_score)


if __name__ == "__main__":
    unittest.main()
