import json
import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.mission import AutonomousPatchRunner, parse_mission
from olympus.agent.mission_checkpoint import MissionCheckpointStore
from olympus.agent.state import AgentState, AgentStatus


class ScriptedPlanner:
    def __init__(self, actions):
        self.actions = list(actions)

    def next_action(self, task, state_summary, context, available_actions):
        return self.actions.pop(0)


class CountingExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, action):
        from olympus.agent.executor import ActionObservation
        self.calls.append(action)
        return ActionObservation(True, action, output="ok")


class OneModelSelector:
    def select_candidates(self, task):
        return ("provider::model",)


class TestReliabilityGateV250(unittest.TestCase):
    def test_action_identity_is_stable_across_models_and_dict_order(self):
        first = AgentAction(
            ActionType.PATCH_FILE,
            "app/index.html",
            {"operation": "replace", "new_content": "ready"},
            metadata={"provider_action_id": "one"},
        )
        second = AgentAction(
            ActionType.PATCH_FILE,
            "app/index.html",
            {"new_content": "ready", "operation": "replace"},
            metadata={"provider_action_id": "two"},
        )
        self.assertEqual(first.idempotency_key, second.idempotency_key)

    def test_resume_does_not_execute_the_same_mutation_twice(self):
        action = AgentAction(
            ActionType.CREATE_FILE,
            "app/index.html",
            "<!doctype html><html><body>Ready</body></html>",
        )
        executor = CountingExecutor()
        planner = ScriptedPlanner([action, AgentAction(ActionType.FINISH)])
        initial = AgentState(
            "create page",
            status=AgentStatus.BLOCKED,
            selected_model="provider::first",
            errors=("provider timeout",),
            metadata={
                "failure_kind": "technical",
                "completed_action_keys": [action.idempotency_key],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp, "app")
            app.mkdir()
            Path(app, "index.html").write_text(
                "<!doctype html><html><body>Ready</body></html>",
                encoding="utf-8",
            )
            result = AgentLoop(tmp, planner, executor=executor).run(
                "create page",
                selected_model="provider::second",
                initial_state=initial,
                max_iterations=3,
            )
        self.assertEqual(
            [item.type for item in executor.calls],
            [ActionType.FINISH],
        )
        self.assertEqual(result.state.status, AgentStatus.COMPLETED)
        self.assertTrue(result.history[0]["idempotent_replay_skipped"])

    def test_action_boundary_progress_is_written_to_mission_checkpoint(self):
        captured_checkpoint = []

        class InterruptAfterProgressLoop:
            def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
                action = AgentAction(
                    ActionType.CREATE_FILE,
                    "app/index.html",
                    "<html>ready</html>",
                )
                state = AgentState(
                    task,
                    selected_model=selected_model,
                    files_modified=("app/index.html",),
                    metadata={"completed_action_keys": [action.idempotency_key]},
                ).next_iteration().transition(AgentStatus.OBSERVING)
                self.progress_callback(state)
                captured_checkpoint.append(True)
                raise RuntimeError("simulated process interruption")

        with tempfile.TemporaryDirectory() as tmp:
            store = MissionCheckpointStore(tmp)
            runner = AutonomousPatchRunner(
                tmp,
                object(),
                selector=OneModelSelector(),
                planner_factory=lambda router, model: object(),
                loop_factory=lambda root, planner: InterruptAfterProgressLoop(),
                checkpoint_store=store,
            )
            result = runner.run(parse_mission("# Demo\nCrie uma landing page completa"))
            checkpoint = store.load("MISSION")

        self.assertFalse(result.success)
        self.assertEqual(captured_checkpoint, [True])
        self.assertEqual(checkpoint.files_modified, ("app/index.html",))
        continuation = checkpoint.metadata["continuation"]
        self.assertEqual(len(continuation["completed_action_keys"]), 1)
        json.dumps(checkpoint.to_dict())


if __name__ == "__main__":
    unittest.main()
