import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.state import AgentStatus
from olympus.agent.verifier import AgentVerifier


TASK = (
    "Crie uma landing page profissional para uma empresa de tecnologia chamada Olympus. "
    "Use fundo escuro, destaque em azul, menu superior, seção principal, três benefícios, "
    "depoimento de cliente e botão de contato. Gere uma interface responsiva."
)

COMPLETE_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#08111f;color:white}nav,main{display:flex}.cards{display:grid}</style></head>
<body><nav>Olympus <a href="#contato">Contato</a></nav><main><section><h1>Tecnologia que transforma</h1>
<p>A Olympus cria produtos digitais seguros, modernos e eficientes para empresas que desejam crescer.</p>
<div class="cards"><article>Velocidade para entregar</article><article>Segurança em cada etapa</article>
<article>Qualidade comprovada</article></div><blockquote>Uma experiência excelente para nossa equipe.</blockquote>
<button id="contato">Fale conosco</button></section></main></body></html>"""


class RepairingPlanner:
    def __init__(self):
        self.actions = [
            AgentAction(ActionType.CREATE_FILE, "app/index.html", "<html><body><h1>Welcome</h1></body></html>"),
            AgentAction(ActionType.FINISH, payload="ready"),
            AgentAction(ActionType.CREATE_FILE, "app/index.html", COMPLETE_HTML),
            AgentAction(ActionType.FINISH, payload="ready"),
        ]

    def next_action(self, task, state_summary, context, available_actions):
        return self.actions.pop(0)


class WebDeliverableQualityV206Tests(unittest.TestCase):
    def test_click_requirement_rejects_static_button_without_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "app" / "index.html"
            page.parent.mkdir(parents=True)
            page.write_text(
                "<!doctype html><html><body><button id='btn-teste'>Testar</button></body></html>",
                encoding="utf-8",
            )
            errors = AgentVerifier(str(root)).verify_task_deliverable(
                "Crie um botão e ao clicar deve exibir 'Botão funcionando'.",
                ("app/index.html",),
            )
            self.assertTrue(any("click interaction" in item for item in errors))

    def test_click_requirement_accepts_inline_behavior_and_expected_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / "app" / "index.html"
            page.parent.mkdir(parents=True)
            page.write_text(
                "<!doctype html><html><head><title>Teste</title></head><body><main><h1>Teste R5</h1><p>Uma página funcional para validar a interação do botão.</p><button onclick=\"this.textContent='Botão funcionando'\">Testar</button></main></body></html>",
                encoding="utf-8",
            )
            errors = AgentVerifier(str(root)).verify_task_deliverable(
                "Crie um botão e ao clicar deve exibir 'Botão funcionando'.",
                ("app/index.html",),
            )
            self.assertEqual(errors, ())

    def test_detailed_request_rejects_welcome_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "app/index.html")
            target.parent.mkdir()
            target.write_text("<html><body><h1>Welcome</h1></body></html>", encoding="utf-8")
            errors = AgentVerifier(tmp).verify_task_deliverable(TASK, ("app/index.html",))
            self.assertTrue(errors)
            self.assertIn("placeholder", errors[0])

    def test_complete_requested_landing_page_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "app/index.html")
            target.parent.mkdir()
            target.write_text(COMPLETE_HTML, encoding="utf-8")
            self.assertEqual(
                AgentVerifier(tmp).verify_task_deliverable(TASK, ("app/index.html",)),
                (),
            )

    def test_portuguese_todo_is_content_not_an_unfinished_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "app/index.html")
            target.parent.mkdir()
            target.write_text(
                COMPLETE_HTML.replace(
                    "A Olympus cria produtos digitais seguros, modernos e eficientes",
                    "A Olympus acompanha todo o processo e cria produtos digitais seguros",
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                AgentVerifier(tmp).verify_task_deliverable(
                    TASK, ("app/index.html",), ("product-experience",)
                ),
                (),
            )

    def test_uppercase_todo_remains_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "app/index.html")
            target.parent.mkdir()
            target.write_text(COMPLETE_HTML.replace("Qualidade comprovada", "TODO"), encoding="utf-8")
            errors = AgentVerifier(tmp).verify_task_deliverable(
                TASK, ("app/index.html",), ("product-experience",)
            )
            self.assertTrue(errors)
            self.assertIn("placeholder", errors[0])

    def test_agent_repairs_placeholder_before_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentLoop(tmp, RepairingPlanner()).run(TASK, max_iterations=6)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertEqual(result.state.iteration, 4)
            self.assertTrue(any("deliverable quality" in error for error in result.state.errors))
            self.assertIn(
                "Tecnologia que transforma",
                Path(tmp, "app/index.html").read_text(encoding="utf-8"),
            )

    def test_multifile_app_rejects_broken_window_data_and_missing_controls(self):
        task = """Crie um aplicativo web com app/index.html, app/styles.css, app/data.js e app/app.js.
        Permita pesquisar e filtrar locais. No mobile, use interface responsiva.
        Permita criar grupo, editar nome, ativar ou desativar, excluir somente
        quando vazio e arquivar. Inclua Restaurar dados de demonstração."""
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp, "app")
            app.mkdir()
            (app / "index.html").write_text(
                "<!doctype html><html><head><meta name='viewport' content='width=device-width'>"
                "<link rel='stylesheet' href='styles.css'></head><body><h1>Gideões</h1>"
                "<nav>Início Locais Histórico Grupos</nav><script src='data.js'></script>"
                "<script src='app.js'></script></body></html>",
                encoding="utf-8",
            )
            (app / "styles.css").write_text("body{color:#222}", encoding="utf-8")
            (app / "data.js").write_text("const locais = [{nome:'Escola'}];", encoding="utf-8")
            (app / "app.js").write_text(
                "if (!window.locais) setTimeout(init, 10);"
                "var s=document.createElement('script');s.src='data.js';",
                encoding="utf-8",
            )
            errors = AgentVerifier(tmp).verify_task_deliverable(
                task,
                ("app/index.html", "app/styles.css", "app/data.js", "app/app.js"),
            )
        self.assertTrue(errors)
        self.assertIn("lexical globals", errors[0])
        self.assertIn("only once", errors[0])
        self.assertIn("mobile responsive", errors[0])
        self.assertIn("search control", errors[0])
        self.assertIn("restore demonstration", errors[0])
        self.assertIn("group management", errors[0])


if __name__ == "__main__":
    unittest.main()
