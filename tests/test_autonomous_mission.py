import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.mission import (
    AutonomousPatchRunner,
    MissionSpecError,
    load_mission,
    parse_mission,
)
from olympus.agent.state import AgentStatus


MISSION = """# PATCH-008 — Autonomous Execution

## STEP 008.1 — Create module
Create a new module.

## STEP 008.2 — Update module
Patch the existing module and test it.
"""


class FakeSelector:
    def __init__(self, model="fake/model"):
        self.model = model
        self.calls = []

    def select(self, task):
        self.calls.append(task)
        return self.model


class ScriptedPlanner:
    def __init__(self, actions):
        self.actions = list(actions)

    def next_action(self, task, state_summary, context, available_actions):
        return self.actions.pop(0)


class TestMissionSpec(unittest.TestCase):
    def test_parse_steps(self):
        mission = parse_mission(MISSION)
        self.assertEqual(mission.id, "PATCH-008")
        self.assertEqual(len(mission.steps), 2)
        self.assertEqual(mission.steps[0].id, "008.1")
        self.assertIn("Create a new module", mission.steps[0].instruction)

    def test_mission_without_steps_becomes_auto_step(self):
        mission = parse_mission("# PATCH-008\nNo explicit steps; implement the objective.")
        self.assertEqual(len(mission.steps), 1)
        self.assertEqual(mission.steps[0].id, "AUTO-1")
        self.assertIn("implement the objective", mission.steps[0].instruction)

    def test_load_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "PATCH.md"
            path.write_text(MISSION)
            self.assertEqual(load_mission(str(path)).id, "PATCH-008")


class TestAutonomousPatchRunner(unittest.TestCase):
    def test_runs_multiple_steps_without_user_intervention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests/__init__.py").write_text("")
            selector = FakeSelector()
            planners = [
                ScriptedPlanner([
                    AgentAction(ActionType.CREATE_FILE, "olympus/value.py", "def value():\n    return 1\n"),
                    AgentAction(ActionType.FINISH, payload="created"),
                ]),
                ScriptedPlanner([
                    AgentAction(ActionType.CREATE_FILE, "tests/test_value.py",
                                "import unittest\nfrom olympus.value import value\n\n"
                                "class TestValue(unittest.TestCase):\n"
                                "    def test_value(self):\n        self.assertEqual(value(), 2)\n"),
                    AgentAction(ActionType.PATCH_FILE, "olympus/value.py", {
                        "operation": "replace_function",
                        "symbol": "value",
                        "new_content": "def value():\n    return 2",
                    }),
                    AgentAction(ActionType.RUN_TEST, "tests.test_value", ["tests.test_value"]),
                    AgentAction(ActionType.FINISH, payload="done"),
                ]),
            ]
            events = []

            def planner_factory(router, model):
                return planners.pop(0)

            runner = AutonomousPatchRunner(
                tmp,
                router=object(),
                selector=selector,
                planner_factory=planner_factory,
                telemetry=events.append,
            )
            result = runner.run(parse_mission(MISSION))

            self.assertTrue(result.success)
            self.assertEqual(len(result.steps), 2)
            self.assertEqual(result.steps[-1].loop_result.state.status, AgentStatus.COMPLETED)
            self.assertIn("return 2", (root / "olympus/value.py").read_text())
            self.assertEqual(len(selector.calls), 2)
            self.assertTrue(all(call.startswith("OLYMPUS_EXECUTION_CONTRACT") for call in selector.calls))
            self.assertIn("Create a new module", selector.calls[0])
            self.assertIn("Patch the existing module and test it", selector.calls[1])
            self.assertEqual(events[0]["event"], "mission_start")
            self.assertEqual(events[-1]["event"], "mission_end")

    def test_stops_after_failed_step(self):
        selector = FakeSelector()

        class FailingLoop:
            def run(self, *args, **kwargs):
                from olympus.agent.loop import AgentLoopResult
                from olympus.agent.state import AgentState
                state = AgentState("x").transition(AgentStatus.FAILED, errors=("boom",))
                return AgentLoopResult(state, ())

        runner = AutonomousPatchRunner(
            ".",
            router=object(),
            selector=selector,
            planner_factory=lambda router, model: object(),
            loop_factory=lambda root, planner: FailingLoop(),
        )
        result = runner.run(parse_mission(MISSION))
        self.assertFalse(result.success)
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.error, "boom")

    def test_technical_model_failure_uses_next_candidate(self):
        class CandidateSelector:
            def select_candidates(self, task):
                return ("model/a", "model/b")

        class TechnicalLoop:
            def __init__(self, model):
                self.model = model

            def run(self, task, selected_model=None, max_iterations=12):
                from olympus.agent.loop import AgentLoopResult
                from olympus.agent.state import AgentState, AgentStatus
                if selected_model == "model/a":
                    state = AgentState(task, selected_model=selected_model).transition(
                        AgentStatus.BLOCKED,
                        errors=("timeout: timed out",),
                        metadata={"failure_kind": "technical"},
                    )
                else:
                    state = AgentState(task, selected_model=selected_model).transition(AgentStatus.COMPLETED)
                return AgentLoopResult(state, ())

        events = []
        runner = AutonomousPatchRunner(
            ".",
            router=object(),
            selector=CandidateSelector(),
            planner_factory=lambda router, model: model,
            loop_factory=lambda root, planner: TechnicalLoop(planner),
            telemetry=events.append,
        )
        result = runner.run(parse_mission("# PATCH-008\nImplement a code change."))
        self.assertTrue(result.success)
        self.assertEqual(result.steps[0].models_attempted, ("model/a", "model/b"))
        self.assertTrue(any(event["event"] == "model_failover" for event in events))


if __name__ == "__main__":
    unittest.main()
