import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.agent.planner import ModelPlanner
from olympus.routing.interfaces import RoutingExecutionResult, RoutingHealth, RoutingModelInfo, ModelCapability
from olympus.routing.omniroute_adapter import OmniRouteAdapter


class NullContentOmniRoute(OmniRouteAdapter):
    def _make_request(self, method, path, body=None):
        return 200, {
            "id": "x",
            "model": "openrouter/test:free",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": None}, "finish_reason": "stop"}],
            "usage": None,
        }


class PlannerRouter:
    def __init__(self):
        self.calls = 0
    def execute(self, model_id, prompt, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return RoutingExecutionResult(model_id, model_id, "fake", None, 1, 0.0, True, None, {}, "success")
        return RoutingExecutionResult(
            model_id, model_id, "fake",
            json.dumps({"type":"finish","target":None,"payload":None,"reason":"done"}),
            1, 0.0, True, None, {}, "success"
        )


class TestRuntimeNullOutputV2715(unittest.TestCase):
    def test_omniroute_null_content_is_not_success(self):
        result = NullContentOmniRoute().execute("Conding-free", "x")
        self.assertFalse(result.success)
        self.assertEqual(result.output, "")
        self.assertEqual(result.status, "malformed_response")

    def test_planner_never_subscripts_none_output(self):
        planner = ModelPlanner(PlannerRouter(), "fake")
        action = planner.next_action("x", "state", type("C", (), {"snippets": {}})(), tuple(__import__('olympus.agent.actions', fromlist=['ActionType']).ActionType))
        self.assertEqual(action.type.value, "finish")


if __name__ == "__main__":
    unittest.main()
