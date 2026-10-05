import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.state import AgentState, AgentStatus


TASK = "Crie uma landing page profissional e responsiva para o Olympus com menu, botão e fundo escuro"
PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Olympus</title><style>body{background:#080d18;color:white;font-family:Arial;padding:2rem}nav{display:flex}main{max-width:960px;margin:auto}button{padding:1rem;background:#38bdf8}@media(max-width:600px){body{padding:1rem}}</style></head>
<body><nav>OLYMPUS</nav><main><h1>Transforme ideias em produtos que funcionam</h1><p>Planeje, construa, teste e publique projetos digitais com automação inteligente, verificação contínua e segurança.</p><section><h2>Uma plataforma completa</h2><p>Crie experiências profissionais com um fluxo claro, confiável e pronto para apresentação.</p><button>Começar um projeto</button></section></main></body></html>"""


class NeverFinishPlanner:
    def next_action(self, task, state_summary, context, available_actions):
        return AgentAction(ActionType.CREATE_FILE, "app/index.html", PAGE, "improve")


class MustNotRunPlanner:
    def next_action(self, *args, **kwargs):
        raise AssertionError("a provider was called even though the result was already valid")


class TestVerifiedCompletionBoundary(unittest.TestCase):
    def test_iteration_boundary_completes_verified_page_without_finish_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentLoop(tmp, NeverFinishPlanner()).run(TASK, max_iterations=2)
        self.assertEqual(result.state.status, AgentStatus.COMPLETED)
        self.assertEqual(result.state.metadata["completion_reason"], "verified_at_iteration_boundary")
        self.assertEqual(result.state.files_modified, ("app/index.html",))

    def test_resume_verifies_existing_page_before_calling_another_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp, "app/index.html")
            page.parent.mkdir(parents=True)
            page.write_text(PAGE, encoding="utf-8")
            initial = AgentState(
                TASK,
                selected_model="groq::first",
                files_modified=("app/index.html",),
                errors=("temporary provider error",),
            )
            result = AgentLoop(tmp, MustNotRunPlanner()).run(
                TASK,
                selected_model="groq::second",
                initial_state=initial,
            )
        self.assertEqual(result.state.status, AgentStatus.COMPLETED)
        self.assertEqual(result.state.metadata["completion_reason"], "verified_before_model_resume")
        self.assertEqual(result.state.iteration, 0)


if __name__ == "__main__":
    unittest.main()
