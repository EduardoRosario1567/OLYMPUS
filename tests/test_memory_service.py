import tempfile, unittest
from unittest.mock import patch
from olympus.memory import *
class TestMemoryService(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.NamedTemporaryFile(suffix='.db'); self.s=MemoryStore(self.t.name); self.w=MemoryWriter(self.s)
 def test_low_auto_confirms(self):
  m=self.w.propose('t1','u1',MemoryType.PREFERENCE,'theme',{'value':'dark'})
  self.assertEqual(m.status,MemoryStatus.CONFIRMED)
 def test_sensitive_is_proposed(self):
  m=self.w.propose('t1','u1',MemoryType.PERSONAL,'x',{'v':1},Sensitivity.HIGH)
  self.assertEqual(m.status,MemoryStatus.PROPOSED)
  self.assertEqual(self.s.list('t1','u1',confirmed_only=True),[])
 def test_never_store_cannot_persist(self):
  with self.assertRaises(PermissionError): self.w.propose('t','u',MemoryType.RULE,'secret',{'v':1},Sensitivity.NEVER_STORE)
  self.assertEqual(self.s.list('t','u'),[])
 def test_tenant_user_project_isolation(self):
  self.w.propose('t1','u1',MemoryType.PROJECT,'a',{'v':1},project_id='p1')
  self.assertEqual(len(self.s.list('t1','u1','p1')),1); self.assertEqual(self.s.list('t2','u1','p1'),[]); self.assertEqual(self.s.list('t1','u2','p1'),[])
 def test_crud_and_confirmation(self):
  m=self.w.propose('t','u',MemoryType.DECISION,'d',{'v':1},Sensitivity.MEDIUM)
  m=self.s.update(m.id,'t','u',status=MemoryStatus.CONFIRMED,value={'v':2}); self.assertEqual(m.value['v'],2)
  self.assertTrue(self.s.delete(m.id,'t','u')); self.assertIsNone(self.s.get(m.id,'t','u'))
 def test_context_only_confirmed_and_relevant(self):
  self.w.propose('t','u',MemoryType.PREFERENCE,'python style',{'style':'typed'})
  self.w.propose('t','u',MemoryType.PERSONAL,'private',{'x':'hidden'},Sensitivity.HIGH)
  c=MemoryContextProvider(self.s).relevant('python implementation','t','u')
  self.assertIn('python style',c); self.assertNotIn('private',c)
 def test_memory_store_factory_keeps_sqlite_local_default(self):
  store=build_memory_store(self.t.name)
  self.assertIsInstance(store,MemoryStore)
 def test_memory_store_factory_recognizes_postgres_dsn(self):
  with patch('olympus.memory.PostgresMemoryStore', return_value='postgres-store') as constructor:
   self.assertEqual(build_memory_store('postgresql://cloud/olympus'),'postgres-store')
   constructor.assert_called_once_with('postgresql://cloud/olympus')
if __name__=='__main__':unittest.main()
