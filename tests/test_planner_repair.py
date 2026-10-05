import unittest
import tempfile
from types import SimpleNamespace

from olympus.agent.actions import ActionType
from olympus.agent.loop import AgentLoop
from olympus.agent.planner import ModelPlanner
from olympus.agent.state import AgentStatus


class RepairRouter:
    def __init__(self):
        self.calls = 0

    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = '{"type":"create_file","payload":"hello"}'
        else:
            output = (
                '{"type":"create_file","target":"app/index.html",'
                '"payload":"hello","reason":"create page"}'
            )
        return SimpleNamespace(success=True, output=output, error=None)


class RepeatedIncompleteWebRouter:
    def __init__(self, repaired_output):
        self.calls = 0
        self.repaired_output = repaired_output

    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        output = '{"type":"create_file","payload":"missing target"}' if self.calls == 1 else self.repaired_output
        return SimpleNamespace(success=True, output=output, error=None)


class RecoverThenFinishRouter:
    def __init__(self):
        self.calls = 0

    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        if self.calls <= 2:
            output = (
                "<!doctype html><html><head><style>body{font-family:sans-serif}</style></head>"
                "<body><h1>Olympus</h1><p>Uma experiência profissional completa para criar, "
                "testar, revisar e publicar projetos digitais com segurança, clareza e velocidade "
                "em uma única plataforma inteligente.</p></body></html>"
            )
        else:
            output = '{"type":"finish","target":null,"payload":"done","reason":"verified"}'
        return SimpleNamespace(success=True, output=output, error=None)


class TestPlannerRepair(unittest.TestCase):
    def test_static_web_repairs_unavailable_run_test_into_create_file(self):
        class Router:
            def __init__(self):
                self.calls = 0
                self.prompts = []

            def execute(self, model_id, prompt, **kwargs):
                self.calls += 1
                self.prompts.append(prompt)
                if self.calls == 1:
                    output = (
                        '{"type":"run_test","target":"index.html",'
                        '"payload":["index.html"],"reason":"verify"}'
                    )
                else:
                    output = (
                        '{"type":"create_file","target":"app/index.html",'
                        '"payload":"<!doctype html><html><body><h1>Olympus</h1></body></html>",'
                        '"reason":"create"}'
                    )
                return SimpleNamespace(success=True, output=output, error=None)

        router = Router()
        action = ModelPlanner(router, "openrouter/openrouter/free").next_action(
            "Crie uma página web",
            "new mission",
            SimpleNamespace(snippets={}),
            (ActionType.CREATE_FILE, ActionType.RUN_TEST, ActionType.FINISH),
        )

        self.assertEqual(action.type, ActionType.CREATE_FILE)
        self.assertEqual(action.target, "app/index.html")
        self.assertEqual(router.calls, 2)
        self.assertNotIn("run_test", router.prompts[0].split("Available actions: ", 1)[1].split("\nTask:", 1)[0])

    def test_requests_enough_output_tokens_for_a_complete_web_document(self):
        class CaptureRouter:
            kwargs = None

            def execute(self, model_id, prompt, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(
                    success=True,
                    output='{"type":"finish","target":null,"payload":null,"reason":"done"}',
                    error=None,
                )

        router = CaptureRouter()
        planner = ModelPlanner(router, "groq::llama-3.3-70b-versatile")
        planner.next_action(
            "Crie uma landing page",
            "already complete",
            SimpleNamespace(snippets={}),
            (ActionType.FINISH,),
        )
        self.assertEqual(router.kwargs["max_tokens"], 8192)  # Web budget established in 2.8.6.
        self.assertEqual(router.kwargs["temperature"], 0.1)

    def test_qwen_free_tier_uses_a_safe_output_budget(self):
        class CaptureRouter:
            kwargs = None

            def execute(self, model_id, prompt, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(
                    success=True,
                    output='{"type":"finish","target":null,"payload":null,"reason":"done"}',
                    error=None,
                )

        router = CaptureRouter()
        planner = ModelPlanner(router, "groq::qwen/qwen3.8-27b")
        planner.next_action(
            "Crie uma landing page",
            "already complete",
            SimpleNamespace(snippets={}),
            (ActionType.FINISH,),
        )
        self.assertEqual(router.kwargs["max_tokens"], 768)

    def test_prompt_budget_caps_state_and_repository_context(self):
        class CaptureRouter:
            def __init__(self):
                self.prompt = ""

            def execute(self, model_id, prompt, **kwargs):
                self.prompt = prompt
                return SimpleNamespace(
                    success=True,
                    output='{"type":"finish","target":null,"payload":null,"reason":"done"}',
                    error=None,
                )

        router = CaptureRouter()
        planner = ModelPlanner(router, "groq::qwen/qwen3-32b")
        planner.next_action(
            "Crie uma página",
            "S" * 12000,
            SimpleNamespace(snippets={"app/index.html": "C" * 12000}),
            (ActionType.CREATE_FILE, ActionType.FINISH),
        )
        self.assertLess(len(router.prompt), 14000)

    def test_repairs_action_missing_target_once(self):
        router = RepairRouter()
        planner = ModelPlanner(router, "openrouter/openrouter/free")

        action = planner.next_action(
            "create a page",
            "new mission",
            SimpleNamespace(snippets={}),
            (ActionType.CREATE_FILE,),
        )

        self.assertEqual(router.calls, 2)
        self.assertEqual(action.target, "app/index.html")
        self.assertEqual(action.payload, "hello")

    def test_recovers_complete_html_when_repair_still_omits_target(self):
        router = RepeatedIncompleteWebRouter(
            '{"type":"create_file","payload":"<!doctype html><html><body>Olympus</body></html>"}'
        )
        planner = ModelPlanner(router, "openrouter/openrouter/free")
        action = planner.next_action(
            "Crie uma landing page profissional",
            "new mission",
            SimpleNamespace(snippets={}),
            (ActionType.CREATE_FILE,),
        )
        self.assertEqual(action.target, "app/index.html")
        self.assertIn("<html>", action.payload)

    def test_preserves_partial_web_draft_when_two_responses_only_omit_target(self):
        router = RepeatedIncompleteWebRouter(
            '{"type":"create_file","payload":"<main><h1>Olympus</h1></main>"}'
        )
        planner = ModelPlanner(router, "groq::qwen/qwen3-32b")
        action = planner.next_action(
            "Crie uma landing page profissional",
            "new mission",
            SimpleNamespace(snippets={}),
            (ActionType.CREATE_FILE,),
        )
        self.assertEqual(action.target, "app/index.html")
        self.assertIn("Olympus", action.payload)

    def test_recovers_complete_html_when_model_explicitly_returns_null_target(self):
        router = RepeatedIncompleteWebRouter(
            '{"type":"create_file","target":null,'
            '"payload":"<!doctype html><html><body>Olympus pronto</body></html>"}'
        )
        planner = ModelPlanner(router, "groq::qwen/qwen3-32b")
        action = planner.next_action(
            "Crie uma landing page profissional",
            "new mission",
            SimpleNamespace(snippets={}),
            (ActionType.CREATE_FILE,),
        )
        self.assertEqual(action.target, "app/index.html")
        self.assertIn("Olympus pronto", action.payload)

    def test_recovers_raw_complete_html_after_invalid_repair(self):
        router = RepeatedIncompleteWebRouter(
            "```html\n<!doctype html><html><body>Olympus</body></html>\n```"
        )
        planner = ModelPlanner(router, "openrouter/openrouter/free")
        action = planner.next_action(
            "Crie uma interface web responsiva",
            "new mission",
            SimpleNamespace(snippets={}),
            (ActionType.CREATE_FILE,),
        )
        self.assertEqual(action.target, "app/index.html")
        self.assertTrue(action.payload.lower().endswith("</html>"))

    def test_does_not_infer_target_for_non_web_or_partial_output(self):
        router = RepeatedIncompleteWebRouter("Aqui está uma sugestão de layout")
        planner = ModelPlanner(router, "openrouter/openrouter/free")
        with self.assertRaises(Exception):
            planner.next_action(
                "Crie uma função Python",
                "new mission",
                SimpleNamespace(snippets={}),
                (ActionType.CREATE_FILE,),
            )

    def test_recovered_document_completes_the_real_agent_loop(self):
        router = RecoverThenFinishRouter()
        with tempfile.TemporaryDirectory() as workspace:
            planner = ModelPlanner(router, "openrouter/openrouter/free")
            result = AgentLoop(workspace, planner).run(
                "Crie uma landing page profissional",
                selected_model="openrouter/openrouter/free",
                max_iterations=3,
            )
        self.assertEqual(result.state.status, AgentStatus.COMPLETED)
        self.assertEqual(result.state.files_modified, ("app/index.html",))
        self.assertEqual(router.calls, 3)


if __name__ == "__main__":
    unittest.main()
