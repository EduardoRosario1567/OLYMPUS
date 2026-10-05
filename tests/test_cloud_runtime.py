import json
import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from olympus.cloud.runtime import CloudRuntime, ExecutionStatus


@dataclass
class FakeResult:
    status: str = "completed"
    success: bool = True
    error: str = None


class FakeRunner:
    calls = []

    def __init__(self, workspace, telemetry):
        self.workspace = workspace
        self.telemetry = telemetry

    def run(self, task, max_iterations=12, resume=True):
        FakeRunner.calls.append((self.workspace, task, max_iterations, resume))
        Path(self.workspace, "generated.txt").write_text("ok", encoding="utf-8")
        self.telemetry({"event": "finish", "status": "completed"})
        return FakeResult()


def factory(workspace, telemetry):
    return FakeRunner(workspace, telemetry)


class TestCloudRuntime(unittest.TestCase):
    def test_execution_history_is_tenant_scoped_and_filterable(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, factory, max_workers=1)
            self.addCleanup(runtime.close)
            first = runtime.store.create("project-a", "mission-a", "A", tenant_id="tenant-a")
            runtime.store.create("project-b", "mission-b", "B", tenant_id="tenant-b")
            runtime.store.update(first.execution_id, status="completed")
            self.assertEqual([item.execution_id for item in runtime.list("tenant-a")], [first.execution_id])
            self.assertEqual(runtime.list("tenant-b", project_id="project-a"), [])
            self.assertEqual([item.execution_id for item in runtime.list("tenant-a", status="completed")], [first.execution_id])

    def test_publish_integration_is_observable_but_never_invalidates_local_result(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, factory, max_workers=1)
            self.addCleanup(runtime.close)
            runtime.add_publish_hook(lambda execution, version: calls.append((execution.project_id, version.version_id)) or {"ok": True})
            runtime.add_publish_hook(lambda execution, version: (_ for _ in ()).throw(RuntimeError("remote unavailable")))
            rec = runtime.submit("integrated", "Create helper")
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status != "completed":
                time.sleep(0.02)
            self.assertEqual(runtime.get(rec.execution_id).status, "completed")
            self.assertEqual(calls[0][0], "integrated")
            events = runtime.events(rec.execution_id)
            self.assertTrue(any(item["event"] == "integration_synced" for item in events))
            failed = next(item for item in events if item["event"] == "integration_failed")
            self.assertEqual(failed["integration"], "github")
            self.assertNotIn("remote unavailable", failed["error"])
            self.assertEqual(failed["error_type"], "RuntimeError")

    def test_submit_is_async_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, factory, max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit("p1", "Create helper", max_iterations=7)
            self.assertIn(rec.status, {"queued", "running", "completed"})
            deadline = time.time() + 2
            current = rec
            while current.status not in {"completed", "failed", "blocked", "cancelled"} and time.time() < deadline:
                time.sleep(0.02)
                current = runtime.get(rec.execution_id)
            self.assertEqual(current.status, "completed")
            self.assertEqual(current.max_iterations, 7)
            self.assertTrue(runtime.events(rec.execution_id))
            self.assertTrue(any(Path(p[0]).parent.name == ".executions" for p in FakeRunner.calls))
            runtime.close()

    def test_each_execution_gets_distinct_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, factory, max_workers=2)
            self.addCleanup(runtime.close)
            a = runtime.submit("p1", "A")
            b = runtime.submit("p2", "B")
            deadline = time.time() + 2
            while time.time() < deadline:
                ra, rb = runtime.get(a.execution_id), runtime.get(b.execution_id)
                if ra.status == "completed" and rb.status == "completed":
                    break
                time.sleep(0.02)
            paths = {p[0] for p in FakeRunner.calls[-2:]}
            self.assertEqual(len(paths), 2)
            runtime.close()

    def test_same_project_rejects_concurrent_execution(self):
        started = Event()
        release = Event()

        class BlockingProjectRunner:
            def __init__(self, workspace, telemetry):
                self.workspace = workspace

            def run(self, task, max_iterations=12, resume=True):
                started.set()
                release.wait(1)
                return FakeResult()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda w, t: BlockingProjectRunner(w, t), max_workers=2)
            self.addCleanup(runtime.close)
            runtime.submit("one-project", "A")
            self.assertTrue(started.wait(1))
            with self.assertRaisesRegex(RuntimeError, "active execution"):
                runtime.submit("one-project", "B")
            release.set()
            runtime.close()

    def test_cancel_marks_execution_cancelled(self):
        started = Event()
        release = Event()

        class BlockingRunner:
            def __init__(self, workspace, telemetry):
                self.workspace = workspace
                self.telemetry = telemetry

            def run(self, task, max_iterations=12, resume=True):
                started.set()
                release.wait(1.5)
                return FakeResult()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda w, t: BlockingRunner(w, t), max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit("p1", "long task")
            self.assertTrue(started.wait(1))
            self.assertTrue(runtime.cancel(rec.execution_id))
            self.assertEqual(runtime.get(rec.execution_id).status, ExecutionStatus.CANCELLED.value)
            release.set()
            time.sleep(0.05)
            self.assertEqual(runtime.get(rec.execution_id).status, ExecutionStatus.CANCELLED.value)
            runtime.close()

    def test_project_busy_tracks_active_and_terminal_executions(self):
        started = Event()
        release = Event()

        class WaitingRunner:
            def __init__(self, workspace, telemetry):
                self.workspace = workspace

            def run(self, task, max_iterations=12, resume=True):
                started.set()
                release.wait(1)
                return FakeResult()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda w, t: WaitingRunner(w, t), max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit("busy-project", "work")
            self.assertTrue(started.wait(1))
            self.assertTrue(runtime.project_is_busy("busy-project"))
            release.set()
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status != "completed":
                time.sleep(0.02)
            self.assertFalse(runtime.project_is_busy("busy-project"))

    def test_resume_requeues_failed_execution(self):
        calls = {"n": 0}

        class FlakyRunner:
            def __init__(self, workspace, telemetry):
                self.workspace = workspace
                self.telemetry = telemetry

            def run(self, task, max_iterations=12, resume=True):
                calls["n"] += 1
                if calls["n"] == 1:
                    return FakeResult(status="failed", success=False, error="transient")
                Path(self.workspace, "generated.txt").write_text("recovered", encoding="utf-8")
                return FakeResult()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, lambda w, t: FlakyRunner(w, t), max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit("p1", "resume me")
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status != "failed":
                time.sleep(0.02)
            self.assertEqual(runtime.get(rec.execution_id).status, "failed")
            resumed = runtime.resume(rec.execution_id)
            self.assertIn(resumed.status, {"queued", "running", "completed"})
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status != "completed":
                time.sleep(0.02)
            self.assertEqual(runtime.get(rec.execution_id).status, "completed")
            self.assertGreaterEqual(runtime.get(rec.execution_id).resume_count, 1)
            runtime.close()


if __name__ == "__main__":
    unittest.main()

class TestCloudRuntimePersistence(unittest.TestCase):
    def test_restart_recovers_interrupted_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            from olympus.cloud.runtime import _Store
            store = _Store(str(Path(tmp) / "runtime.sqlite3"))
            rec = store.create("p1", "m1", "task", max_iterations=9)
            store.update(rec.execution_id, status="running")
            self.assertEqual(store.recover_interrupted(), 1)
            self.assertEqual(store.get(rec.execution_id).status, "queued")

    def test_event_cursor_is_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            from olympus.cloud.runtime import _Store
            store = _Store(str(Path(tmp) / "runtime.sqlite3"))
            rec = store.create("p1", "m2", "task")
            store.event(rec.execution_id, "running")
            store.event(rec.execution_id, "finished", status="completed")
            events = store.events(rec.execution_id, after=2)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "finished")



class TestDurableQueue(unittest.TestCase):
    def test_claim_is_atomic_across_runtime_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            from olympus.cloud.runtime import _Store
            path = str(Path(tmp) / "runtime.sqlite3")
            store_a = _Store(path)
            store_b = _Store(path)
            rec = store_a.create("p1", "m1", "task")
            claimed_a = store_a.claim("worker-a", lease_seconds=60)
            claimed_b = store_b.claim("worker-b", lease_seconds=60)
            self.assertEqual(claimed_a.execution_id, rec.execution_id)
            self.assertIsNone(claimed_b)
            self.assertEqual(store_a.get(rec.execution_id).attempt_count, 1)

    def test_expired_lease_is_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            from olympus.cloud.runtime import _Store
            store = _Store(str(Path(tmp) / "runtime.sqlite3"))
            rec = store.create("p1", "m1", "task")
            claimed = store.claim("worker-a", lease_seconds=0)
            self.assertEqual(claimed.execution_id, rec.execution_id)
            recovered = store.recover_interrupted(lease_seconds=0)
            self.assertEqual(recovered, 1)
            self.assertEqual(store.get(rec.execution_id).status, "queued")
            self.assertIsNone(store.get(rec.execution_id).lease_until)

    def test_lease_renewal_prevents_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            from olympus.cloud.runtime import _Store
            store = _Store(str(Path(tmp) / "runtime.sqlite3"))
            rec = store.create("p1", "m1", "task")
            claimed = store.claim("worker-a", lease_seconds=60)
            self.assertTrue(store.renew_lease(rec.execution_id, 60))
            self.assertEqual(store.recover_interrupted(), 0)
            self.assertEqual(store.get(rec.execution_id).status, "running")

    def test_worker_exception_requeues_with_workspace_preserved(self):
        calls = {"n": 0, "workspace": None, "workspaces": []}

        class CrashOnceRunner:
            def __init__(self, workspace, telemetry):
                calls["n"] += 1
                calls["workspace"] = workspace
                calls["workspaces"].append(workspace)
                Path(workspace, "checkpoint.txt").write_text("safe", encoding="utf-8")
                if calls["n"] == 1:
                    raise RuntimeError("worker crash")

            def run(self, task, max_iterations=12, resume=True):
                return FakeResult()

        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(
                tmp,
                lambda workspace, telemetry: CrashOnceRunner(workspace, telemetry),
                max_workers=1,
                lease_seconds=5,
                max_worker_retries=1,
            )
            self.addCleanup(runtime.close)
            rec = runtime.submit("p1", "recover me")
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status != "completed":
                time.sleep(0.02)
            self.assertEqual(runtime.get(rec.execution_id).status, "completed")
            self.assertGreaterEqual(runtime.get(rec.execution_id).attempt_count, 2)
            self.assertEqual(len(calls["workspaces"]), 2)
            self.assertEqual(calls["workspaces"][0], calls["workspaces"][1])
            runtime.close()

class TestCloudProjectIntegration(unittest.TestCase):
    def test_submit_creates_project_and_execution_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, factory, max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit("project-x", "Create helper")
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status not in {"completed", "failed", "blocked", "cancelled"}:
                time.sleep(0.02)
            project = runtime.projects.get("project-x")
            self.assertIsNotNone(project)
            execution_dir = Path(project.root) / ".executions" / rec.execution_id
            self.assertTrue(execution_dir.is_dir())

    def test_project_workspace_survives_execution_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = CloudRuntime(tmp, factory, max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit("project-y", "Create helper")
            deadline = time.time() + 2
            while time.time() < deadline and runtime.get(rec.execution_id).status != "completed":
                time.sleep(0.02)
            project = runtime.projects.get("project-y")
            execution_dir = Path(project.root) / ".executions" / rec.execution_id
            self.assertTrue((execution_dir / "generated.txt").is_file())
