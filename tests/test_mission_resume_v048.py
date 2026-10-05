import json
import tempfile
import unittest
from pathlib import Path

from olympus.agent.loop import AgentLoopResult
from olympus.agent.mission import AutonomousPatchRunner, parse_mission
from olympus.agent.mission_checkpoint import MissionCheckpoint, MissionCheckpointStore
from olympus.agent.state import AgentState, AgentStatus

MISSION = """# PATCH-048\n\n## STEP 1 — First\nDo first.\n\n## STEP 2 — Second\nDo second.\n\n## STEP 3 — Third\nDo third.\n"""

class Selector:
    def select_candidates(self, task):
        return ("model/a",)

class TwoModelSelector:
    def select_candidates(self, task):
        return ("model/a", "model/b")

class Loop:
    def __init__(self, calls): self.calls=calls
    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        self.calls.append(task)
        state=AgentState(task, selected_model=selected_model).transition(AgentStatus.COMPLETED)
        return AgentLoopResult(state, ())

class TestMissionResume(unittest.TestCase):
    def test_checkpoint_store_round_trip_and_atomic_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=MissionCheckpointStore(tmp)
            cp=MissionCheckpoint("PATCH-1", ("1",), "2", "running", ("m",), ("a.py",), ("tests.x",))
            path=store.save(cp)
            self.assertTrue(path.is_file())
            self.assertEqual(store.load("PATCH-1"), cp)
            json.loads(path.read_text())

    def test_resume_skips_verified_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=MissionCheckpointStore(tmp)
            store.save(MissionCheckpoint("PATCH-048", ("1",), None, "running"))
            calls=[]; events=[]
            runner=AutonomousPatchRunner(
                tmp, object(), selector=Selector(),
                planner_factory=lambda r,m: object(),
                loop_factory=lambda root,planner: Loop(calls),
                telemetry=events.append, checkpoint_store=store,
            )
            result=runner.run(parse_mission(MISSION))
            self.assertTrue(result.success)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(call.startswith("OLYMPUS_EXECUTION_CONTRACT") for call in calls))
            self.assertIn("Do second", calls[0])
            self.assertIn("Do third", calls[1])
            self.assertTrue(any(e["event"]=="step_resume_skip" and e["step"]=="1" for e in events))
            self.assertEqual(store.load("PATCH-048").status, "completed")

    def test_interrupted_active_step_is_replayed_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=MissionCheckpointStore(tmp)
            store.save(MissionCheckpoint("PATCH-048", ("1",), "2", "running", metadata={"resume_policy":"replay_active_step"}))
            calls=[]
            runner=AutonomousPatchRunner(
                tmp, object(), selector=Selector(), planner_factory=lambda r,m: object(),
                loop_factory=lambda root,planner: Loop(calls), checkpoint_store=store,
            )
            self.assertTrue(runner.run(parse_mission(MISSION)).success)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(call.startswith("OLYMPUS_EXECUTION_CONTRACT") for call in calls))
            self.assertIn("Do second", calls[0])
            self.assertIn("Do third", calls[1])

    def test_resume_restores_verified_progress_with_fresh_iteration_budget(self):
        captured = []

        class CaptureLoop:
            def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
                captured.append(initial_state)
                state = (
                    initial_state.resume_for_model(selected_model)
                    if initial_state is not None
                    else AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
                ).transition(AgentStatus.COMPLETED)
                return AgentLoopResult(state, ())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app").mkdir()
            (root / "app/index.html").write_text("<html></html>", encoding="utf-8")
            store = MissionCheckpointStore(tmp)
            store.save(MissionCheckpoint(
                "PATCH-048", ("1",), "2", "blocked", ("model/a",),
                ("app/index.html",), (), "iteration budget exhausted",
                {"resume_policy": "replay_active_step"},
            ))
            runner = AutonomousPatchRunner(
                tmp, object(), selector=Selector(), planner_factory=lambda r, m: object(),
                loop_factory=lambda root, planner: CaptureLoop(), checkpoint_store=store,
            )
            self.assertTrue(runner.run(parse_mission(MISSION)).success)
            final_checkpoint = store.load("PATCH-048")
            self.assertEqual(final_checkpoint.status, "completed")
            self.assertEqual(final_checkpoint.files_modified, ("app/index.html",))
        self.assertIsNotNone(captured[0])
        self.assertEqual(captured[0].iteration, 0)
        self.assertEqual(captured[0].files_modified, ("app/index.html",))

    def test_resume_continues_with_untried_model_and_carries_last_error(self):
        captured = []

        class CaptureLoop:
            def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
                captured.append((selected_model, initial_state))
                state = (
                    initial_state.resume_for_model(selected_model)
                    if initial_state is not None
                    else AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
                ).transition(AgentStatus.COMPLETED)
                return AgentLoopResult(state, ())

        with tempfile.TemporaryDirectory() as tmp:
            store = MissionCheckpointStore(tmp)
            store.save(MissionCheckpoint(
                mission_id="PATCH-048",
                completed_step_ids=("1",),
                active_step_id="2",
                status="blocked",
                models_attempted=("model/a",),
                files_read=("app/index.html",),
                files_modified=("app/index.html",),
                last_error="429 rate limit",
                metadata={"resume_policy": "replay_active_step"},
            ))
            runner = AutonomousPatchRunner(
                tmp, object(), selector=TwoModelSelector(), planner_factory=lambda r,m: object(),
                loop_factory=lambda root,planner: CaptureLoop(), checkpoint_store=store,
            )
            self.assertTrue(runner.run(parse_mission(MISSION)).success)

        selected_model, initial_state = captured[0]
        self.assertEqual(selected_model, "model/b")
        self.assertEqual(initial_state.files_read, ("app/index.html",))
        self.assertEqual(initial_state.files_modified, ("app/index.html",))
        self.assertEqual(initial_state.errors, ("429 rate limit",))

    def test_failure_checkpoint_preserves_last_error(self):
        class FailLoop:
            def run(self, task, **kwargs):
                state=AgentState(task).transition(AgentStatus.FAILED, errors=("semantic failure",))
                return AgentLoopResult(state, ())
        with tempfile.TemporaryDirectory() as tmp:
            store=MissionCheckpointStore(tmp)
            runner=AutonomousPatchRunner(
                tmp, object(), selector=Selector(), planner_factory=lambda r,m: object(),
                loop_factory=lambda root,planner: FailLoop(), checkpoint_store=store,
            )
            result=runner.run(parse_mission(MISSION))
            self.assertFalse(result.success)
            cp=store.load("PATCH-048")
            self.assertEqual(cp.status, "failed")
            self.assertEqual(cp.active_step_id, "1")
            self.assertEqual(cp.last_error, "semantic failure")

if __name__ == '__main__': unittest.main()
