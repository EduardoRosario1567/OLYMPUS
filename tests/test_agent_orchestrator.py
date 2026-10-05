import tempfile
import unittest

from olympus.agent.orchestrator import OlympusAgent
from olympus.routing.interfaces import RoutingExecutionResult


class FakeRouter:
    def execute(self, model_id, prompt, **kwargs):
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model="fake/model",
            provider="fake",
            output=(
                "=== FILE: olympus/agent/generated.py ===\n"
                "VALUE = 1\n"
            ),
            latency_ms=1,
            cost=0.0,
            success=True,
            error=None,
            metadata={},
            status="success",
        )


class FakeTestRunner:
    def __init__(self, success=True):
        self.success = success

    def run_unittest(self, modules):
        class Result:
            pass

        result = Result()
        result.success = self.success
        result.stdout = ""
        result.stderr = "" if self.success else "test failed"
        return result


class TestOlympusAgent(unittest.TestCase):

    def test_full_success_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = OlympusAgent(
                FakeRouter(),
                "fake/model",
                tmp,
            )

            agent.test_runner = FakeTestRunner(True)

            result = agent.run(
                task="Create VALUE",
                target="olympus/agent/generated.py",
                allowed_paths=["olympus/agent/generated.py"],
                test_modules=["tests.test_generated"],
            )

            self.assertTrue(result.success)
            self.assertTrue(result.tests_passed)
            self.assertEqual(
                result.files_modified,
                ("olympus/agent/generated.py",),
            )

    def test_test_failure_triggers_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = OlympusAgent(
                FakeRouter(),
                "fake/model",
                tmp,
            )

            # Initial test fails.
            agent.test_runner = FakeTestRunner(False)

            class FakeRepairLoop:
                def __init__(self, *args, **kwargs):
                    pass

                def repair(self, **kwargs):
                    class Result:
                        success = True
                        cycles = 1
                        files_modified = (
                            "olympus/agent/generated.py",
                        )
                        tests_passed = True
                        error = None

                    return Result()

            import olympus.agent.orchestrator as module

            original = module.RepairLoop
            module.RepairLoop = FakeRepairLoop

            try:
                result = agent.run(
                    task="Create VALUE",
                    target="olympus/agent/generated.py",
                    allowed_paths=[
                        "olympus/agent/generated.py"
                    ],
                    test_modules=[
                        "tests.test_generated"
                    ],
                )
            finally:
                module.RepairLoop = original

            self.assertTrue(result.success)
            self.assertTrue(result.tests_passed)
            self.assertEqual(result.repair_cycles, 1)


if __name__ == "__main__":
    unittest.main()
