import unittest

from olympus.agent.actions import ActionType
from olympus.agent.action_normalizer import normalize_action_data


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


if __name__ == "__main__":
    unittest.main()
