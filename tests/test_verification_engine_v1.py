import tempfile
import unittest
from pathlib import Path

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.state import AgentStatus
from olympus.agent.verification_engine import (
    CheckStatus, VerificationCheck, VerificationEngine, VerificationEvidence,
    VerificationPlan, VerificationStatus,
)


class ScriptedPlanner:
    def __init__(self, actions): self.actions = list(actions)
    def next_action(self, *args): return self.actions.pop(0)


class TestVerificationEngineV1(unittest.TestCase):
    def test_full_evidence_authorizes_completion(self):
        engine = VerificationEngine()
        report = engine.evaluate(VerificationPlan((
            VerificationCheck("acceptance", CheckStatus.PASS, (VerificationEvidence("acceptance", "4/4 criteria"),)),
            VerificationCheck("tests", CheckStatus.PASS, (VerificationEvidence("tests", "38/38 passed"),)),
        )))
        self.assertEqual(report.status, VerificationStatus.FULL)
        self.assertTrue(report.completed)
        self.assertEqual(report.confidence, 1.0)

    def test_failure_never_completes_even_with_other_evidence(self):
        report = VerificationEngine().evaluate(VerificationPlan((
            VerificationCheck("acceptance", CheckStatus.PASS),
            VerificationCheck("tests", CheckStatus.FAIL),
        )))
        self.assertEqual(report.status, VerificationStatus.FAILED)
        self.assertFalse(report.completed)

    def test_no_evidence_is_not_completion(self):
        report = VerificationEngine().evaluate(VerificationPlan(()))
        self.assertEqual(report.status, VerificationStatus.NONE)
        self.assertFalse(report.completed)
        self.assertEqual(report.confidence, 0.0)

    def test_finish_is_request_to_verify_not_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = ScriptedPlanner([AgentAction(ActionType.FINISH, payload="I am done")])
            result = AgentLoop(tmp, planner).run("claim completion without evidence", max_iterations=1)
            self.assertNotEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertIn("verification", result.state.metadata)

    def test_verified_code_persists_structured_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            planner = ScriptedPlanner([
                AgentAction(ActionType.CREATE_FILE, "olympus/value.py", "VALUE = 1\n"),
                AgentAction(ActionType.FINISH, payload="done"),
            ])
            result = AgentLoop(tmp, planner).run("create verified code", max_iterations=3)
            self.assertEqual(result.state.status, AgentStatus.COMPLETED)
            self.assertEqual(result.state.metadata["verification"]["status"], "full")
            self.assertGreater(len(result.state.metadata["verification"]["evidence"]), 0)
