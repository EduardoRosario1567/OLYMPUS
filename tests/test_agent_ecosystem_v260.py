import unittest
from pathlib import Path

from olympus.skills import SkillRegistry, SkillResolver


EXPECTED = {
    "systematic-delivery",
    "product-sprint",
    "spec-driven-development",
    "context-efficiency",
    "checkpoint-continuity",
    "social-media-strategy",
    "exposure-audit",
    "answer-first",
}


class AgentEcosystemV260Tests(unittest.TestCase):
    def setUp(self):
        self.registry = SkillRegistry()
        self.resolver = SkillResolver(self.registry)

    def test_native_capabilities_are_active_complete_contracts(self):
        self.assertTrue(EXPECTED.issubset(set(self.registry.ids())))
        for skill_id in EXPECTED:
            skill = self.registry.get(skill_id)
            self.assertEqual(skill.source, "builtin")
            self.assertEqual(skill.status, "active")
            self.assertTrue(skill.triggers)
            self.assertTrue(skill.guidance)
            self.assertTrue(skill.constraints)
            self.assertTrue(skill.completion_checks)

    def test_each_capability_routes_from_a_specific_request(self):
        cases = {
            "systematic-delivery": "Use TDD com red green refactor nesta correção",
            "product-sprint": "Faça uma entrega ponta a ponta usando product sprint",
            "spec-driven-development": "Use Spec Kit e critérios de aceite antes do código",
            "context-efficiency": "Reduzir tokens com um contexto compacto",
            "checkpoint-continuity": "Use checkpoint para continuar de onde parou se o modelo falhou",
            "social-media-strategy": "Crie um calendário editorial para Instagram",
            "exposure-audit": "Faça uma auditoria de exposição para encontrar chaves expostas",
            "answer-first": "Seja direto e comece pela resposta",
        }
        for expected, task in cases.items():
            with self.subTest(skill=expected):
                resolved = {skill.id for skill in self.resolver.resolve(task)}
                self.assertIn(expected, resolved)

    def test_checkpoint_and_context_skills_encode_failover_invariants(self):
        checkpoint = self.registry.get("checkpoint-continuity")
        context = self.registry.get("context-efficiency")
        combined = " ".join(checkpoint.guidance + checkpoint.completion_checks + context.guidance + context.completion_checks).lower()
        self.assertIn("idempotency", combined)
        self.assertIn("next provider", combined)
        self.assertIn("smallest context", combined)

    def test_repositories_are_attributed_only_where_concepts_were_adapted(self):
        sources = {
            "systematic-delivery": "https://github.com/obra/superpowers",
            "product-sprint": "https://github.com/garrytan/gstack",
            "spec-driven-development": "https://github.com/github/spec-kit",
            "social-media-strategy": "https://github.com/social-media-skills/skills",
        }
        for skill_id, source_url in sources.items():
            skill = self.registry.get(skill_id)
            self.assertEqual(skill.source_url, source_url)
            self.assertIn("MIT", skill.license)

    def test_skills_screen_explains_the_three_integration_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "app" / "skills" / "page.tsx").read_text(encoding="utf-8")
        self.assertIn("Skills", source)
        self.assertIn("MCP e conectores", source)
        self.assertIn("Apps e bibliotecas", source)
        self.assertIn("servidor detectado", source)


if __name__ == "__main__":
    unittest.main()
