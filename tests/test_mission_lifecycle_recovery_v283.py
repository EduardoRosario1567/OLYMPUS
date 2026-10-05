import tempfile, time, unittest
from pathlib import Path
from olympus.cloud.runtime import CloudRuntime, ExecutionStatus, _Store

class TestMissionLifecycleRecoveryV283(unittest.TestCase):
    def test_legacy_waiting_capacity_is_parked_on_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=_Store(str(Path(tmp)/'cloud_runtime.sqlite3'))
            rec=store.create('rosales','m1','landing')
            store.update(rec.execution_id,status='waiting_capacity',error='technical_failure: connection refused',resume_count=2,lease_until=time.time()+3600,lease_owner='old-worker')
            rt=CloudRuntime(tmp, lambda w,t: None, max_workers=1)
            self.addCleanup(rt.close)
            cur=rt.get(rec.execution_id)
            self.assertEqual(cur.status, ExecutionStatus.PAUSED_CAPACITY.value)
            self.assertIsNone(cur.lease_owner)
            self.assertFalse(rt.project_is_busy('rosales'))

    def test_frontend_treats_legacy_waiting_capacity_as_terminal(self):
        src=Path('frontend/app/missao/page.tsx').read_text(encoding='utf-8')
        self.assertIn('"waiting_capacity"', src)
        self.assertIn('execution?.status === "waiting_capacity"', src)

if __name__=='__main__': unittest.main()
