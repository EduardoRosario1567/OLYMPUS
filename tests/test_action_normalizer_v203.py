import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.action_normalizer import normalize_action_data
from olympus.agent.executor import ActionExecutor
from olympus.agent.planner import ModelPlanner


class TestActionNormalizerV203(unittest.TestCase):
    def test_accepts_file_path_and_parameters(self):
        action = normalize_action_data({
            "name": "write_file",
            "parameters": {"file_path": "app/index.html", "content": "<html></html>"},
        })
        self.assertEqual(action.type, ActionType.CREATE_FILE)
        self.assertEqual(action.target, "app/index.html")
        self.assertEqual(action.payload, "<html></html>")

    def test_accepts_single_tool_call_function(self):
        action = normalize_action_data({
            "tool_calls": [{
                "function": {
                    "name": "write_file",
                    "arguments": {"target_path": "app/index.html", "content": "ok"},
                }
            }]
        })
        self.assertEqual(action.target, "app/index.html")
        self.assertEqual(action.payload, "ok")

    def test_accepts_single_action_array(self):
        action = normalize_action_data([{
            "type": "create_file", "file_path": "app/index.html", "content": "ok",
        }])
        self.assertEqual(action.target, "app/index.html")

    def test_accepts_nested_action_object(self):
        action = normalize_action_data({
            "action": {"type": "create_file", "path": "app/index.html", "content": "ok"},
        })
        self.assertEqual(action.type, ActionType.CREATE_FILE)
        self.assertEqual(action.target, "app/index.html")

    def test_accepts_json_encoded_function_arguments(self):
        action = normalize_action_data({
            "function": {
                "name": "write_file",
                "arguments": '{"file_path":"app/index.html","content":"ok"}',
            }
        })
        self.assertEqual(action.target, "app/index.html")
        self.assertEqual(action.payload, "ok")


    def test_patch_payload_decodes_json_string(self):
        action = normalize_action_data({
            "type": "patch_file",
            "target": "src/main.py",
            "payload": json.dumps({
                "operation": "append_block",
                "new_content": "value = 2",
            }),
        })
        self.assertEqual(action.type, ActionType.PATCH_FILE)
        self.assertEqual(action.payload["operation"], "append_block")
        self.assertEqual(action.payload["new_content"], "value = 2")

    def test_patch_payload_normalizes_aliases(self):
        action = normalize_action_data({
            "type": "patch_file",
            "target": "src/main.py",
            "payload": {
                "edit": "replace_function",
                "function": "value",
                "content": "def value():\n    return 7",
                "file_path": "src/main.py",
            },
        })
        self.assertEqual(
            action.payload,
            {
                "operation": "replace_function",
                "symbol": "value",
                "new_content": "def value():\n    return 7",
            },
        )

    def test_patch_payload_accepts_unique_old_text_new_text(self):
        action = normalize_action_data({
            "type": "patch_file",
            "target": "src/main.py",
            "payload": {
                "old_text": "value = 1",
                "new_text": "value = 7",
            },
        })

        self.assertEqual(
            action.payload,
            {
                "operation": "replace_text",
                "old_text": "value = 1",
                "new_content": "value = 7",
            },
        )

    def test_executor_replace_text_is_exact_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()

            target = root / "src" / "main.py"
            target.write_text(
                "value = 1\nother = 2\n",
                encoding="utf-8",
            )

            action = normalize_action_data({
                "type": "patch_file",
                "target": "src/main.py",
                "payload": {
                    "old_text": "value = 1",
                    "new_text": "value = 7",
                },
            })

            observation = ActionExecutor(tmp).execute(action)

            self.assertTrue(observation.success, observation.error)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "value = 7\nother = 2\n",
            )

            target.write_text(
                "value = 1\nvalue = 1\n",
                encoding="utf-8",
            )

            ambiguous = normalize_action_data({
                "type": "patch_file",
                "target": "src/main.py",
                "payload": {
                    "old_text": "value = 1",
                    "new_text": "value = 9",
                },
            })

            rejected = ActionExecutor(tmp).execute(ambiguous)

            self.assertFalse(rejected.success)
            self.assertIn(
                "exactly one old_text match",
                rejected.error,
            )
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "value = 1\nvalue = 1\n",
            )

    def test_patch_payload_rejects_free_text(self):
        with self.assertRaisesRegex(
            ValueError,
            "patch_file payload must be an object",
        ):
            normalize_action_data({
                "type": "patch_file",
                "target": "src/main.py",
                "payload": "troque a linha",
            })

    def test_patch_replace_lines_requires_valid_range(self):
        with self.assertRaisesRegex(
            ValueError,
            "requires valid start_line/end_line",
        ):
            normalize_action_data({
                "type": "patch_file",
                "target": "src/main.py",
                "payload": {
                    "operation": "replace_lines",
                    "new_content": "value = 2",
                },
            })

    def test_executor_defensively_rejects_invalid_direct_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text(
                "value = 1\n",
                encoding="utf-8",
            )
            observation = ActionExecutor(tmp).execute(
                AgentAction(
                    ActionType.PATCH_FILE,
                    "src/main.py",
                    "invalid patch payload",
                )
            )
            self.assertFalse(observation.success)
            self.assertEqual(
                observation.error,
                "patch_file payload must be an object",
            )
            self.assertEqual(
                (root / "src" / "main.py").read_text(encoding="utf-8"),
                "value = 1\n",
            )

    def test_planner_repairs_invalid_patch_contract(self):
        class Router:
            def __init__(self):
                self.calls = 0

            def execute(self, model_id, prompt, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    output = json.dumps({
                        "type": "patch_file",
                        "target": "src/main.py",
                        "payload": "replace value",
                    })
                else:
                    output = json.dumps({
                        "type": "patch_file",
                        "target": "src/main.py",
                        "payload": {
                            "operation": "replace_lines",
                            "start_line": 1,
                            "end_line": 1,
                            "new_content": "value = 7",
                        },
                    })
                return SimpleNamespace(
                    success=True,
                    output=output,
                    error=None,
                    actual_model=model_id,
                    provider="fixture",
                )

        router = Router()
        planner = ModelPlanner(router, "fixture::model")
        action = planner.next_action(
            "Atualize src/main.py",
            "{}",
            SimpleNamespace(snippets={}),
            (ActionType.PATCH_FILE,),
        )

        self.assertEqual(router.calls, 2)
        self.assertEqual(action.type, ActionType.PATCH_FILE)
        self.assertEqual(action.payload["operation"], "replace_lines")
        self.assertEqual(action.payload["start_line"], 1)
        self.assertEqual(action.payload["end_line"], 1)


if __name__ == "__main__":
    unittest.main()
