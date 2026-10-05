import tempfile
import unittest
from pathlib import Path

from olympus.agent.repair_loop import RepairLoop
from olympus.routing.interfaces import RoutingExecutionResult


class FakeRouter:
    def execute(self, model_id, prompt, **kwargs):
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model="fake/model",
            provider="fake",
            output=(
                "=== FILE: olympus/agent/example.py ===\n"
                "VALUE = 2\n"
            ),
            latency_ms=1,
            cost=0.0,
            success=True,
            error=None,
            metadata={},
            status="success",
        )


class FakeTests:
    def __init__(self):
        self.calls = 0

    def run_unittest(self, modules):
        self.calls += 1

        class Result:
            pass

        result = Result()
        result.success = True
        result.stdout = ""
        result.stderr = ""
        return result


class TestRepairLoop(unittest.TestCase):

    def test_repairs_and_retests(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "olympus/agent/example.py"
            target.parent.mkdir(parents=True)
            target.write_text("VALUE = 1\n")

            loop = RepairLoop(
                FakeRouter(),
                "fake/model",
                tmp,
            )
            loop.test_runner = FakeTests()

            result = loop.repair(
                task="VALUE must be 2",
                target="olympus/agent/example.py",
                allowed_paths=["olympus/agent/example.py"],
                test_modules=["tests.test_example"],
                initial_error="expected 2, got 1",
            )

            self.assertTrue(result.success)
            self.assertEqual(result.cycles, 1)
            self.assertTrue(result.tests_passed)
            self.assertEqual(
                target.read_text(),
                "VALUE = 2\n",
            )

    def test_max_cycles_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                RepairLoop(
                    FakeRouter(),
                    "fake/model",
                    tmp,
                    max_cycles=4,
                )


if __name__ == "__main__":
    unittest.main()
