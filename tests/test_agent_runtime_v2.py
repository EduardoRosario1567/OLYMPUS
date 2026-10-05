import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.autonomy import AutonomyDecision, AutonomyPolicy
from olympus.agent.context_engine import ContextEngine
from olympus.agent.executor import ActionExecutor
from olympus.agent.loop import AgentLoop
from olympus.agent.patch_engine import PatchEngine, PatchEngineError, PatchRequest
from olympus.agent.planner import ModelPlanner, PlannerError
from olympus.agent.repo_map import build_repo_map
from olympus.agent.state import AgentState, AgentStatus


class TestStateActions(unittest.TestCase):
    def test_state_is_immutable_and_transitions(self):
        state = AgentState("task")
        next_state = state.transition(AgentStatus.PLANNING)
        self.assertEqual(state.status, AgentStatus.CREATED)
        self.assertEqual(next_state.status, AgentStatus.PLANNING)

    def test_iteration_limit_blocks(self):
        state = AgentState("task", iteration=1, max_iterations=1)
        blocked = state.next_iteration()
        self.assertEqual(blocked.status, AgentStatus.BLOCKED)

    def test_action_requires_target(self):
        with self.assertRaises(ValueError):
            AgentAction(ActionType.READ_FILE)


class TestRepoMapContext(unittest.TestCase):
    def test_ast_map_and_context_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            (root / "tests").mkdir()
            (root / "olympus/example.py").write_text("import os\n\ndef hello(name):\n    return name\n")
            (root / "tests/test_example.py").write_text("def test_hello():\n    pass\n")
            repo = build_repo_map(tmp)
            self.assertEqual(repo.find_symbol("hello")[0].path, "olympus/example.py")
            self.assertEqual(repo.find_test_for_file("olympus/example.py"), "tests/test_example.py")
            context = ContextEngine(tmp, max_files=2, max_chars=80, max_lines=10).resolve(
                "Change olympus/example.py hello", repo
            )
            self.assertIn("olympus/example.py", context.selected_files)
            self.assertLessEqual(context.budget_usage["files"], 2)
            self.assertLessEqual(context.budget_usage["chars"], 80)
            self.assertEqual(context.selection_reasons["olympus/example.py"], "explicit_path")


class TestPatchEngine(unittest.TestCase):
    def test_replace_function_by_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            target = root / "olympus/a.py"
            target.write_text("def value():\n    return 1\n")
            engine = PatchEngine(tmp, ["olympus/"])
            engine.apply(PatchRequest("olympus/a.py", "replace_function", "def value():\n    return 2", symbol="value"))
            self.assertIn("return 2", target.read_text())

    def test_invalid_python_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            (root / "olympus/a.py").write_text("x = 1\n")
            engine = PatchEngine(tmp, ["olympus/"])
            with self.assertRaises(PatchEngineError):
                engine.apply(PatchRequest("olympus/a.py", "append_block", "def broken("))

    def test_outside_workspace_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = PatchEngine(tmp, ["olympus/"])
            with self.assertRaises(Exception):
                engine.apply(PatchRequest("../evil.py", "append_block", "x=1"))


class TestAutonomyExecutor(unittest.TestCase):
    def test_dangerous_action_blocked(self):
        action = AgentAction(ActionType.PATCH_FILE, "olympus/a.py", {"new_content": "rm -rf /"})
        self.assertEqual(AutonomyPolicy().evaluate(action).decision, AutonomyDecision.BLOCK)

    def test_css_form_selector_is_not_mistaken_for_rm_command(self):
        action = AgentAction(
            ActionType.PATCH_FILE,
            "app/index.html",
            {"new_content": ".form { display: grid; }"},
        )
        self.assertEqual(AutonomyPolicy().evaluate(action).decision, AutonomyDecision.ALLOW)

    def test_create_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = ActionExecutor(tmp)
            create = AgentAction(ActionType.CREATE_FILE, "olympus/a.py", "VALUE = 1\n")
            self.assertTrue(executor.execute(create).success)
            read = AgentAction(ActionType.READ_FILE, "olympus/a.py")
            result = executor.execute(read)
            self.assertTrue(result.success)
            self.assertIn("VALUE", result.output)

    def test_create_and_search_frontend_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = ActionExecutor(tmp)
            create = AgentAction(
                ActionType.CREATE_FILE,
                "app/index.html",
                "<button>Pesquisar</button>",
            )
            self.assertTrue(executor.execute(create).success)
            search = AgentAction(ActionType.SEARCH_CODE, "app", "Pesquisar")
            result = executor.execute(search)
            self.assertTrue(result.success)
            self.assertEqual(result.output[0][0], "app/index.html")


class TestPlanner(unittest.TestCase):
    def test_parse_action(self):
        action = ModelPlanner.parse_action('{"type":"finish","target":null,"payload":"done","reason":"ok"}')
        self.assertEqual(action.type, ActionType.FINISH)

    def test_malformed_action(self):
        with self.assertRaises(PlannerError):
            ModelPlanner.parse_action("not json")


class ScriptedPlanner:
    def __init__(self, actions):
        self.actions = list(actions)

    def next_action(self, task, state_summary, context, available_actions):
        return self.actions.pop(0)


class SummaryAwarePlanner:
    def __init__(self):
        self.calls = 0

    def next_action(self, task, state_summary, context, available_actions):
        self.calls += 1
        if self.calls == 1:
            return AgentAction(ActionType.CREATE_FILE, "app/index.html", "<!doctype html><html><body>Uma página completa pronta para uso</body></html>")
        self.last_summary = state_summary
        return AgentAction(ActionType.FINISH, payload="done")


class TestAgentLoop(unittest.TestCase):
    def test_rejected_test_target_is_not_persisted_or_replayed(self):
        class InvalidTestPlanner:
            def next_action(self, task, state_summary, context, available_actions):
                return AgentAction(
                    ActionType.RUN_TEST,
                    "index.html",
                    ["index.html"],
                )

        with tempfile.TemporaryDirectory() as tmp:
            result = AgentLoop(tmp, InvalidTestPlanner()).run(
                "validate a page",
                max_iterations=1,
            )

        self.assertEqual(result.state.status, AgentStatus.BLOCKED)
        self.assertEqual(result.state.tests_run, ())
        self.assertIn(
            "only tests.* modules are allowed",
            " ".join(result.state.errors),
        )

    def test_create_then_finish_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = ScriptedPlanner([
                AgentAction(ActionType.CREATE_FILE, "olympus/generated.py", "VALUE = 42\n"),
                AgentAction(ActionType.FINISH, payload="done"),
            ])
            result = AgentLoop(tmp, planner).run("create value", max_iterations=4)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertTrue((Path(tmp) / "olympus/generated.py").exists())
            self.assertEqual(len(result.history), 2)

    def test_existing_file_patch_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            (root / "olympus/a.py").write_text("def value():\n    return 1\n")
            planner = ScriptedPlanner([
                AgentAction(ActionType.PATCH_FILE, "olympus/a.py", {
                    "operation": "replace_function",
                    "symbol": "value",
                    "new_content": "def value():\n    return 2",
                }),
                AgentAction(ActionType.FINISH, payload="done"),
            ])
            result = AgentLoop(tmp, planner).run("change value", max_iterations=4)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertIn("return 2", (root / "olympus/a.py").read_text())

    def test_create_patch_test_finish_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests/__init__.py").write_text("")
            planner = ScriptedPlanner([
                AgentAction(ActionType.CREATE_FILE, "olympus/counter.py", "def value():\n    return 1\n"),
                AgentAction(ActionType.CREATE_FILE, "tests/test_counter.py",
                            "import unittest\nfrom olympus.counter import value\n\n"
                            "class TestCounter(unittest.TestCase):\n"
                            "    def test_value(self):\n        self.assertEqual(value(), 2)\n"),
                AgentAction(ActionType.PATCH_FILE, "olympus/counter.py", {
                    "operation": "replace_function",
                    "symbol": "value",
                    "new_content": "def value():\n    return 2",
                }),
                AgentAction(ActionType.RUN_TEST, "tests.test_counter", ["tests.test_counter"]),
                AgentAction(ActionType.FINISH, payload="done"),
            ])
            result = AgentLoop(tmp, planner).run("create patch test finish", max_iterations=8)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertIn("olympus/counter.py", result.state.files_modified)
            self.assertIn("tests/test_counter.py", result.state.files_modified)
            self.assertIn("tests.test_counter", result.state.tests_run)
            self.assertIn("return 2", (root / "olympus/counter.py").read_text())
            self.assertEqual([item["action"] for item in result.history], [
                "create_file", "create_file", "patch_file", "run_test", "finish"
            ])

    def test_iteration_budget_prevents_infinite_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = ScriptedPlanner([
                AgentAction(ActionType.INSPECT_RESULT, payload="x"),
                AgentAction(ActionType.INSPECT_RESULT, payload="x"),
                AgentAction(ActionType.INSPECT_RESULT, payload="x"),
            ])
            result = AgentLoop(tmp, planner).run("loop", max_iterations=2)
            self.assertEqual(result.state.status, AgentStatus.BLOCKED)
            self.assertEqual(result.state.iteration, 2)

    def test_repeated_inspection_of_verified_change_completes_without_exhausting_budget(self):
        class InspectingPlanner:
            calls = 0

            def next_action(self, task, state_summary, context, available_actions):
                self.calls += 1
                if self.calls == 1:
                    return AgentAction(
                        ActionType.CREATE_FILE,
                        "app/index.html",
                        "<!doctype html><html><body>Ready</body></html>",
                    )
                return AgentAction(ActionType.INSPECT_RESULT, payload="looks ready")

        with tempfile.TemporaryDirectory() as tmp:
            result = AgentLoop(tmp, InspectingPlanner()).run("create page", max_iterations=12)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertEqual(result.state.iteration, 3)
            self.assertEqual(
                result.state.metadata["completion_reason"],
                "verified_repeated_inspection",
            )

    def test_planner_receives_progress_and_completion_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = SummaryAwarePlanner()
            result = AgentLoop(tmp, planner).run("Crie uma página", max_iterations=3)
        self.assertEqual(result.state.status, AgentStatus.COMPLETED)
        self.assertIn('"files_modified": ["app/index.html"]', planner.last_summary)
        self.assertIn('"completion_rule"', planner.last_summary)


if __name__ == "__main__":
    unittest.main()



class TestPlannerNormalization(unittest.TestCase):
    def test_parse_fenced_json(self):
        action = ModelPlanner.parse_action(
            '```json\n{"type":"finish","target":null,"payload":"done","reason":"ok"}\n```'
        )
        self.assertEqual(action.type, ActionType.FINISH)

    def test_parse_json_with_surrounding_text(self):
        action = ModelPlanner.parse_action(
            'Next action:\n{"type":"finish","target":null,"payload":"done","reason":"ok"}\nProceed.'
        )
        self.assertEqual(action.type, ActionType.FINISH)

    def test_promotes_nested_create_file_path_and_content(self):
        action = ModelPlanner.parse_action(
            '{"type":"create_file","payload":'
            '{"path":"app/index.html","content":"<h1>OK</h1>"}}'
        )
        self.assertEqual(action.type, ActionType.CREATE_FILE)
        self.assertEqual(action.target, "app/index.html")
        self.assertEqual(action.payload, "<h1>OK</h1>")

class TestActionProtocol(unittest.TestCase):
    def test_uses_first_action_when_model_returns_a_plan_array(self):
        action = ModelPlanner.parse_action(
            '[{"type":"create_file","target":"app/index.html","payload":"<h1>Primeiro</h1>"},'
            '{"type":"finish","target":null}]'
        )
        self.assertEqual(action.type, ActionType.CREATE_FILE)
        self.assertEqual(action.target, "app/index.html")

    def test_accepts_namespaced_tool_name(self):
        action = ModelPlanner.parse_action(
            '{"name":"repo_browser.search_code","arguments":{"path":"app","query":"Olympus"}}'
        )
        self.assertEqual(action.type, ActionType.SEARCH_CODE)
        self.assertEqual(action.target, "app")

    def test_action_aliases_are_normalized(self):
        action = ModelPlanner.parse_action(
            '{"action":"edit","path":"olympus/a.py","arguments":'
            '{"operation":"replace_function","function":"value",'
            '"content":"def value():\\n    return 2"}}'
        )
        self.assertEqual(action.type, ActionType.PATCH_FILE)
        self.assertEqual(action.target, "olympus/a.py")
        self.assertEqual(action.payload["operation"], "replace_function")
        self.assertEqual(action.payload["symbol"], "value")
        self.assertIn("return 2", action.payload["new_content"])

    def test_nested_tool_call_is_normalized(self):
        action = ModelPlanner.parse_action(
            '```json\\n{"tool_call":{"name":"search","path":"olympus/agent"}}\\n```'
        )
        self.assertEqual(action.type, ActionType.SEARCH_CODE)
        self.assertEqual(action.target, "olympus/agent")

    def test_conflicting_action_types_are_rejected(self):
        with self.assertRaises(PlannerError):
            ModelPlanner.parse_action(
                '{"type":"read_file","action":"finish","target":"x"}'
            )
