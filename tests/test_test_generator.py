import tempfile
import unittest
from pathlib import Path

from olympus.agent.test_generator import AcceptanceTestGenerator
from olympus.routing.interfaces import RoutingExecutionResult


class FakeRouter:

    def execute(self, model_id, prompt, **kwargs):
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model="fake/model",
            provider="fake",
            output=(
                "=== FILE: tests/test_example.py ===\n"
                "import unittest\n\n"
                "class TestExample(unittest.TestCase):\n"
                "    def test_requirement(self):\n"
                "        self.assertTrue(True)\n"
            ),
            latency_ms=1,
            cost=0.0,
            success=True,
            error=None,
            metadata={},
            status="success",
        )


class TestAcceptanceTestGenerator(unittest.TestCase):

    def test_generates_only_expected_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            generator = AcceptanceTestGenerator(
                FakeRouter(),
                "fake/model",
                tmp,
            )

            module = generator.generate(
                "Create example",
                "olympus/agent/example.py",
            )

            self.assertEqual(
                module,
                "tests.test_example",
            )

            self.assertTrue(
                (
                    Path(tmp)
                    / "tests/test_example.py"
                ).exists()
            )

    def test_blocks_unsafe_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            generator = AcceptanceTestGenerator(
                FakeRouter(),
                "fake/model",
                tmp,
            )

            with self.assertRaises(Exception):
                generator.generate(
                    "bad",
                    "../evil.py",
                )


if __name__ == "__main__":
    unittest.main()
