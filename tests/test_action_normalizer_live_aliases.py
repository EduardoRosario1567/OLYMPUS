import unittest

from olympus.agent.actions import ActionType
from olympus.agent.action_normalizer import normalize_action_text


class TestActionNormalizerLiveAliases(unittest.TestCase):
    def test_open_file_from_live_groq_trace_is_read_file(self):
        action = normalize_action_text(
            '{"type":"open_file","target":"app/index.html","reason":"inspect"}'
        )
        self.assertEqual(action.type, ActionType.READ_FILE)
        self.assertEqual(action.target, "app/index.html")


if __name__ == "__main__":
    unittest.main()
