import tempfile
import json
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.mission import AutonomousPatchRunner, MissionSpec, MissionStep
from olympus.agent.state import AgentStatus
from olympus.agent.verifier import AgentVerifier
from olympus.skills import SkillRegistry, SkillResolver


TASK = (
    "Crie uma landing page profissional para a empresa Olympus, com menu, seção principal, "
    "três benefícios, depoimento, botão de contato e uma interface responsiva."
)

PROFESSIONAL_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Olympus — Tecnologia confiável</title><style>
:root{--bg:#07111f;--surface:#10233b;--text:#eef7ff;--muted:#aac0d5;--accent:#38a9ff;--space:clamp(1rem,3vw,3rem)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif;line-height:1.6}
nav,main,footer{width:min(1120px,calc(100% - 2rem));margin:auto}nav{display:flex;align-items:center;justify-content:space-between;padding:1.25rem 0}
a,button{border-radius:.7rem;padding:.8rem 1rem;background:var(--accent);color:#03101c;text-decoration:none;border:0;font-weight:700}
.hero{padding:5rem 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}.card{background:var(--surface);padding:1.5rem;border-radius:1rem}
blockquote{margin:3rem 0;padding:1.5rem;border-left:3px solid var(--accent);color:var(--muted)}footer{padding:2rem 0;color:var(--muted)}
@media(max-width:700px){nav{align-items:flex-start}.hero{padding:3rem 0}.grid{grid-template-columns:1fr}h1{font-size:2rem}}
</style></head><body><nav aria-label="Principal"><strong>Olympus</strong><a href="#contato">Contato</a></nav>
<main><section class="hero"><p>Software criado para empresas ambiciosas</p><h1>Transforme ideias em experiências digitais confiáveis</h1>
<p>A Olympus une estratégia, engenharia e automação para entregar produtos seguros, rápidos e fáceis de usar.</p><a href="#contato">Converse com nossa equipe</a></section>
<section aria-labelledby="beneficios"><h2 id="beneficios">Resultados que acompanham seu crescimento</h2><div class="grid">
<article class="card"><h3>Velocidade</h3><p>Automação responsável reduz o tempo entre a decisão e uma entrega validada.</p></article>
<article class="card"><h3>Segurança</h3><p>Controles e versões preservam cada etapa importante do seu projeto.</p></article>
<article class="card"><h3>Qualidade</h3><p>Revisões objetivas transformam requisitos em experiências consistentes.</p></article></div></section>
<section><h2>Confiança de quem constrói conosco</h2><blockquote>“A Olympus tornou nosso processo claro e entregou uma experiência que nossos clientes realmente entendem.” — Marina, diretora de produto</blockquote></section>
<section id="contato"><h2>Pronto para começar?</h2><p>Conte seu objetivo e receba um caminho claro para a próxima entrega.</p><button type="button">Solicitar contato</button></section></main>
<footer>Olympus · Tecnologia com propósito · Todos os direitos reservados.</footer></body></html>"""


class ContractPlanner:
    def __init__(self):
        self.summaries = []
        self.actions = [
            AgentAction(ActionType.CREATE_FILE, "docs/delivery-concept.md", "# Visual thesis\nA restrained product page with a clear accent and readable hierarchy.\n# Content plan\nBrand, benefits, evidence and contact.\n# Interaction plan\nNavigation targets named sections.\n# Evidence\nFixture content only; browser and visual review pending.\n"),
            AgentAction(ActionType.CREATE_FILE, "app/index.html", PROFESSIONAL_HTML),
            AgentAction(ActionType.FINISH, payload="ready"),
        ]

    def next_action(self, task, state_summary, context, available_actions):
        self.summaries.append(state_summary)
        return self.actions.pop(0)


class OneModelSelector:
    def select_candidates(self, task):
        return ("test/model",)


class ProfessionalSkillContractV207Tests(unittest.TestCase):
    def setUp(self):
        self.skills = SkillResolver(SkillRegistry()).resolve(TASK)
        self.ids = tuple(skill.id for skill in self.skills)
        self.contract = {
            "ids": list(self.ids),
            "guidance": [item for skill in self.skills for item in skill.guidance],
            "completion_checks": [item for skill in self.skills for item in skill.completion_checks],
        }

    def test_frontend_composes_professional_experience_skills(self):
        self.assertIn("frontend", self.ids)
        self.assertIn("testing", self.ids)
        self.assertIn("product-experience", self.ids)
        self.assertIn("visual-design", self.ids)
        self.assertIn("accessibility", self.ids)
        self.assertTrue(self.contract["guidance"])
        self.assertTrue(self.contract["completion_checks"])

    def test_placeholder_is_rejected_by_professional_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "app/index.html")
            target.parent.mkdir()
            target.write_text("<html><body><h1>Welcome</h1></body></html>", encoding="utf-8")
            errors = AgentVerifier(tmp).verify_task_deliverable(TASK, ("app/index.html",), self.ids)
            self.assertTrue(errors)
            self.assertIn("placeholder", errors[0])

    def test_professional_contract_reaches_planner_and_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = ContractPlanner()
            result = AgentLoop(tmp, planner, skill_context=self.contract).run(TASK, max_iterations=4)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertIn("professional_skill_contract", planner.summaries[0])
            self.assertEqual(set(result.state.metadata["active_skills"]), set(self.ids))

    def test_mission_runner_automatically_injects_resolved_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = ContractPlanner()
            runner = AutonomousPatchRunner(
                tmp,
                router=object(),
                selector=OneModelSelector(),
                planner_factory=lambda router, model: planner,
            )
            mission = MissionSpec("SKILL-E2E", "Skill E2E", (MissionStep("1", "Build", TASK, 4),))
            result = runner.run(mission, resume=False)
            self.assertTrue(result.success)
            metadata = result.steps[0].loop_result.state.metadata
            self.assertEqual(set(metadata["active_skills"]), set(self.ids))
            self.assertIn("Product Experience", planner.summaries[0])
            guidance = json.loads(planner.summaries[0])["professional_skill_contract"]["guidance"]
            self.assertTrue(any("Wikimedia" in line for line in guidance[:8]))


if __name__ == "__main__":
    unittest.main()
