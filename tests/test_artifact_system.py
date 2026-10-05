import tempfile, unittest
from pathlib import Path
from olympus.artifacts import ArtifactStore, ArtifactType, artifact_evidence
from olympus.agent.verification_engine import VerificationEngine, VerificationPlan, VerificationStatus

class ArtifactSystemTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); root=Path(self.t.name)
        self.store=ArtifactStore(str(root/'a.db'),str(root/'objects'))
    def tearDown(self): self.t.cleanup()
    def test_create_and_version(self):
        a=self.store.create('t1','p1','m1','e1',ArtifactType.DOCUMENT,'report.txt',b'one')
        b=self.store.create('t1','p1','m1','e2',ArtifactType.DOCUMENT,'report.txt',b'two')
        self.assertEqual((a.version,b.version),(1,2)); self.assertNotEqual(a.sha256,b.sha256)
    def test_tenant_isolation(self):
        a=self.store.create('t1','p','m','e',ArtifactType.DATA,'x.json',b'{}')
        self.assertIsNone(self.store.get(a.id,'t2')); self.assertEqual(self.store.list('t2'),[])
    def test_safe_name_and_controlled_path(self):
        a=self.store.create('t','p','m','e',ArtifactType.CODE,'../../escape.py',b'x=1')
        self.assertEqual(a.name,'escape.py'); self.assertTrue(str(self.store.content_path(a.id,'t')).startswith(str(self.store.storage_root)))
    def test_delete_removes_metadata_and_content(self):
        a=self.store.create('t','p','m','e',ArtifactType.IMAGE,'x.png',b'png')
        p=self.store.content_path(a.id,'t'); self.assertTrue(p.exists()); self.assertTrue(self.store.delete(a.id,'t')); self.assertFalse(p.exists()); self.assertIsNone(self.store.get(a.id,'t'))
    def test_verification_integration(self):
        a=self.store.create('t','p','m','e',ArtifactType.SPREADSHEET,'x.csv',b'a,b\n1,2\n')
        check=artifact_evidence(self.store,a.id,'t'); report=VerificationEngine().evaluate(VerificationPlan((check,)))
        self.assertEqual(report.status,VerificationStatus.FULL); self.assertTrue(report.completed)
    def test_integrity_failure_blocks_full(self):
        a=self.store.create('t','p','m','e',ArtifactType.OTHER,'x.bin',b'good')
        self.store.content_path(a.id,'t').write_bytes(b'bad')
        report=VerificationEngine().evaluate(VerificationPlan((artifact_evidence(self.store,a.id,'t'),)))
        self.assertEqual(report.status,VerificationStatus.FAILED); self.assertFalse(report.completed)
if __name__=='__main__':unittest.main()
