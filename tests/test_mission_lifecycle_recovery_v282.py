import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

from olympus.cloud.runtime import CloudRuntime, ExecutionStatus, _Store


@dataclass
class Result:
    status: str
    success: bool
    error: str | None = None


class TestMissionLifecycleRecoveryV282(unittest.TestCase):
    def test_capacity_retry_is_bounded_then_project_is_released(self):
        calls = {"n": 0}

        class CapacityRunner:
            def __init__(self, workspace, telemetry):
                self.workspace = workspace

            def run(self, task, max_iterations=12, resume=True):
                calls["n"] += 1
                return Result(
                    status="blocked",
                    success=False,
                    error="technical_failure: <urlopen error [Errno 61] Connection refused>",
                )

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda w, t: CapacityRunner(w, t), max_workers=1)
            self.addCleanup(runtime.close)
            runtime.max_capacity_resumes = 1
            runtime.capacity_retry_seconds = 0.05
            rec = runtime.submit("rosales", "Crie uma landing page")
            deadline = time.time() + 3
            current = runtime.get(rec.execution_id)
            while time.time() < deadline and current.status != ExecutionStatus.PAUSED_CAPACITY.value:
                time.sleep(0.02)
                current = runtime.get(rec.execution_id)
            self.assertEqual(current.status, ExecutionStatus.PAUSED_CAPACITY.value)
            self.assertEqual(current.resume_count, 1)
            self.assertFalse(runtime.project_is_busy("rosales"))
            events = runtime.events(rec.execution_id)
            self.assertTrue(any(e["event"] == "waiting_for_capacity" for e in events))
            self.assertTrue(any(e["event"] == "capacity_paused" for e in events))
            self.assertEqual(calls["n"], 2)

    def test_startup_releases_stale_capacity_lock_from_previous_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _Store(str(Path(tmp) / "cloud_runtime.sqlite3"))
            rec = store.create("rosales", "m1", "landing")
            store.update(
                rec.execution_id,
                status=ExecutionStatus.RUNNING.value,
                error="technical_failure: <urlopen error [Errno 61] Connection refused>",
                resume_count=1,
                lease_until=time.time() + 3600,
                lease_owner="old-worker",
            )
            runtime = CloudRuntime(tmp, lambda w, t: None, max_workers=1)
            self.addCleanup(runtime.close)
            recovered = runtime.get(rec.execution_id)
            self.assertEqual(recovered.status, ExecutionStatus.PAUSED_CAPACITY.value)
            self.assertIsNone(recovered.lease_owner)
            self.assertFalse(runtime.project_is_busy("rosales"))
            self.assertTrue(any(e["event"] == "capacity_paused" for e in runtime.events(rec.execution_id)))

    def test_paused_capacity_can_be_resumed_manually(self):
        calls = {"n": 0}

        class ResumeRunner:
            def __init__(self, workspace, telemetry):
                self.workspace = workspace

            def run(self, task, max_iterations=12, resume=True):
                calls["n"] += 1
                Path(self.workspace, "index.html").write_text(
                    "<!doctype html><html><head><title>Rosales</title></head><body><main><h1>Rosales Café</h1></main></body></html>",
                    encoding="utf-8",
                )
                return Result(status="completed", success=True)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda w, t: ResumeRunner(w, t), max_workers=1)
            self.addCleanup(runtime.close)
            runtime.max_workers = 0
            runtime.projects.ensure("rosales")
            rec = runtime.store.create("rosales", "m1", "Crie uma landing page")
            workspace = runtime.projects.execution_workspace("rosales", rec.execution_id)
            workspace.mkdir(parents=True, exist_ok=True)
            runtime.store.update(rec.execution_id, workspace=str(workspace), status=ExecutionStatus.PAUSED_CAPACITY.value, error="timeout", resume_count=1)
            runtime.max_workers = 1
            resumed = runtime.resume(rec.execution_id)
            self.assertIn(resumed.status, {"queued", "running", "completed"})
            deadline = time.time() + 3
            while time.time() < deadline and runtime.get(rec.execution_id).status not in {"completed", "failed"}:
                time.sleep(0.02)
            final = runtime.get(rec.execution_id)
            self.assertIn(final.status, {"completed", "failed"})
            self.assertEqual(calls["n"], 1)
            self.assertNotEqual(final.status, ExecutionStatus.PAUSED_CAPACITY.value)

    def test_frontend_hydrates_existing_execution_and_knows_paused_capacity(self):
        source = Path("frontend/app/missao/page.tsx").read_text(encoding="utf-8")
        self.assertIn('"paused_capacity"', source)
        self.assertIn("listarCloudExecucoes({ project_id: projectId, limit: 1 })", source)
        self.assertIn("capacity_paused", source)
        self.assertIn("waiting_for_capacity", source)


if __name__ == "__main__":
    unittest.main()
