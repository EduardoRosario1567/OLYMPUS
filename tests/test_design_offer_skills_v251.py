import unittest

from olympus.skills import SkillRegistry, SkillResolver


EXPECTED = {
    "offer-engineering",
    "emil-design-eng",
    "ui-ux-pro-max",
    "web-design-guidelines",
    "brandkit",
    "extract-design-system",
    "image-to-code",
}


class DesignOfferSkillsV251Tests(unittest.TestCase):
    def setUp(self):
        self.registry = SkillRegistry()
        self.resolver = SkillResolver(self.registry)

    def test_all_seven_skills_are_builtin_active_contracts(self):
        self.assertTrue(EXPECTED.issubset(set(self.registry.ids())))
        for skill_id in EXPECTED:
            skill = self.registry.get(skill_id)
            self.assertEqual(skill.source, "builtin")
            self.assertEqual(skill.status, "active")
            self.assertTrue(skill.guidance)
            self.assertTrue(skill.completion_checks)
            self.assertTrue(skill.constraints)

    def test_offer_engineering_routes_commercial_offer_work(self):
        ids = {
            skill.id for skill in self.resolver.resolve(
                "Crie uma proposta comercial com oferta, bônus, garantia e objeções"
            )
        }
        self.assertIn("offer-engineering", ids)
        self.assertIn("product-experience", ids)
        self.assertIn("testing", ids)

    def test_each_design_capability_has_a_discriminating_trigger(self):
        cases = {
            "emil-design-eng": "Revise o easing e a duração da animação",
            "ui-ux-pro-max": "Crie um design system para uma interface profissional",
            "web-design-guidelines": "Faça uma auditoria de design e revisar interface",
            "brandkit": "Crie um brand kit e manual de marca",
            "extract-design-system": "Extrair tokens.json e tokens.css deste site de referência",
            "image-to-code": "Converta este screenshot para código responsivo",
        }
        for expected, task in cases.items():
            with self.subTest(skill=expected):
                ids = {skill.id for skill in self.resolver.resolve(task)}
                self.assertIn(expected, ids)

    def test_external_inspirations_keep_source_and_license_visible(self):
        for skill_id in EXPECTED - {"offer-engineering"}:
            skill = self.registry.get(skill_id)
            self.assertTrue(skill.source_url.startswith("https://github.com/"))
            self.assertIn("MIT", skill.license)


if __name__ == "__main__":
    unittest.main()
