import tempfile
import unittest
from pathlib import Path

from olympus.agent.dev_agent import OlympusDevAgent
from olympus.routing.interfaces import RoutingExecutionResult


class FakeRouter:
    def __init__(self, output):
        self.output = output

    def execute(self, model_id, prompt, **kwargs):
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model="fake/model",
            provider="fake",
            output=self.output,
            latency_ms=10,
            cost=0.0,
            success=True,
            error=None,
            metadata={},
            status="success",
        )


class TestOlympusDevAgent(unittest.TestCase):

    def test_applies_allowed_file(self):
        output = (
            "=== FILE: olympus/agent/generated.py ===\n"
            "def soma(a, b):\n"
            "    return a + b\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            agent = OlympusDevAgent(
                router=FakeRouter(output),
                model_id="fake/model",
                root=tmp,
            )

            result = agent.run(
                task="Create soma function",
                target="olympus/agent/generated.py",
                allowed_paths=["olympus/agent/generated.py"],
            )

            self.assertTrue(result.success)

            target = Path(tmp) / "olympus/agent/generated.py"

            self.assertTrue(target.exists())
            self.assertIn(
                "def soma",
                target.read_text(encoding="utf-8"),
            )

    def test_blocks_outside_scope(self):
        output = (
            "=== FILE: backend/evil.py ===\n"
            "print('bad')\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            agent = OlympusDevAgent(
                router=FakeRouter(output),
                model_id="fake/model",
                root=tmp,
            )

            result = agent.run(
                task="malicious",
                target="olympus/agent/generated.py",
                allowed_paths=["olympus/agent/"],
            )

            self.assertFalse(result.success)
            self.assertEqual(result.execution_status, "blocked")

    def test_preserves_model_metadata(self):
        output = (
            "=== FILE: olympus/agent/generated.py ===\n"
            "x = 1\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            agent = OlympusDevAgent(
                router=FakeRouter(output),
                model_id="requested/model",
                root=tmp,
            )

            result = agent.run(
                task="test",
                target="olympus/agent/generated.py",
                allowed_paths=["olympus/agent/"],
            )

            self.assertEqual(
                result.requested_model,
                "requested/model",
            )
            self.assertEqual(
                result.actual_model,
                "fake/model",
            )


if __name__ == "__main__":
    unittest.main()
