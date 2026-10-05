import tempfile
import unittest

from olympus.cloud.runtime import CloudRuntime


class TestBudgetResumeV204(unittest.TestCase):
    def test_budget_exhaustion_resume_expands_to_24(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda workspace, telemetry: object(), max_workers=1)
            runtime._closed = True
            record = runtime.store.create("project", "mission", "task", max_iterations=12)
            runtime.store.update(record.execution_id, status="blocked", error="iteration budget exhausted")
            resumed = runtime.resume(record.execution_id)
            self.assertEqual(resumed.status, "queued")
            self.assertEqual(resumed.max_iterations, 24)
            runtime.close()

    def test_other_failures_preserve_configured_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda workspace, telemetry: object(), max_workers=1)
            runtime._closed = True
            record = runtime.store.create("project", "mission", "task", max_iterations=7)
            runtime.store.update(record.execution_id, status="blocked", error="provider unavailable")
            resumed = runtime.resume(record.execution_id)
            self.assertEqual(resumed.max_iterations, 7)
            runtime.close()


if __name__ == "__main__":
    unittest.main()
