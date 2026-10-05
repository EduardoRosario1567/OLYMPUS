import tempfile
import time
import unittest

from olympus.cloud.runtime import CloudRuntime, ExecutionStatus


class DummyRunner:
    def run(self, *args, **kwargs):
        raise AssertionError("worker should not run in decision protocol unit tests")


class HumanDecisionProtocolTests(unittest.TestCase):
    def make_runtime(self):
        td = tempfile.TemporaryDirectory()
        rt = CloudRuntime(td.name, lambda workspace, telemetry: DummyRunner(), max_workers=1)
        self.addCleanup(rt.close)
        self.addCleanup(td.cleanup)
        rt.projects.create("tenant-a", "project-a", "Project A")
        rec = rt.store.create("project-a", "mission-a", "choose safely", tenant_id="tenant-a")
        return rt, rec

    def test_request_pauses_execution_and_emits_event(self):
        rt, rec = self.make_runtime()
        req = rt.request_decision(rec.execution_id, "Choose", [{"id":"a"},{"id":"b"}])
        self.assertEqual(rt.get(rec.execution_id).status, ExecutionStatus.WAITING_DECISION.value)
        self.assertEqual(rt.events(rec.execution_id)[-1]["event"], "decision_requested")
        self.assertEqual(req.tenant_id, "tenant-a")

    def test_answer_resumes_exactly_once(self):
        rt, rec = self.make_runtime()
        req = rt.request_decision(rec.execution_id, "Choose", [{"id":"a"}])
        rt.answer_decision(rec.execution_id, req.decision_id, "tenant-a", "a")
        updated = rt.get(rec.execution_id)
        self.assertEqual(updated.status, ExecutionStatus.QUEUED.value)
        self.assertEqual(updated.resume_count, 1)
        with self.assertRaises(RuntimeError):
            rt.answer_decision(rec.execution_id, req.decision_id, "tenant-a", "a")

    def test_cross_tenant_answer_is_hidden(self):
        rt, rec = self.make_runtime()
        req = rt.request_decision(rec.execution_id, "Choose", [{"id":"a"}])
        with self.assertRaises(KeyError):
            rt.answer_decision(rec.execution_id, req.decision_id, "tenant-b", "a")
        self.assertEqual(rt.get(rec.execution_id).status, ExecutionStatus.WAITING_DECISION.value)

    def test_expired_decision_cannot_be_answered(self):
        rt, rec = self.make_runtime()
        req = rt.request_decision(rec.execution_id, "Choose", [{"id":"a"}], ttl_seconds=-1)
        with self.assertRaises(TimeoutError):
            rt.answer_decision(rec.execution_id, req.decision_id, "tenant-a", "a")
        self.assertEqual(rt.get(rec.execution_id).status, ExecutionStatus.WAITING_DECISION.value)

    def test_decision_is_auditable(self):
        rt, rec = self.make_runtime()
        req = rt.request_decision(rec.execution_id, "Choose", [{"id":"a"}], {"reason":"irreversible"})
        rt.answer_decision(rec.execution_id, req.decision_id, "tenant-a", {"id":"a"}, "approved")
        names = [e["event"] for e in rt.events(rec.execution_id)]
        self.assertIn("decision_requested", names)
        self.assertIn("decision_answered", names)
        self.assertIn("resumed_after_decision", names)


if __name__ == "__main__":
    unittest.main()
