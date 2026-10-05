import hashlib,json,tempfile,unittest
from pathlib import Path
from olympus.agent.mission_compiler import MissionCompiler
from olympus.agent.test_runner import TargetedTestRunner
from olympus.agent.executor import ActionExecutor
from olympus.agent.actions import AgentAction,ActionType

class MethodValidationTests(unittest.TestCase):
    def test_explicit_frabic_update_identifies_method_and_preserves_objective(self):
        request='Faça uma nova versão utilizando as skills Frabic'
        c=MissionCompiler().compile(request)
        data=json.loads(c.instruction().split('\n',1)[1])
        self.assertEqual(data['objective'],request)
        self.assertEqual(c.original_sha256,hashlib.sha256(request.encode()).hexdigest())
        constraints=' '.join(data['constraints'])
        self.assertIn('Superpowers',constraints)
        self.assertIn('Microsoft Fabric UI',constraints)
        self.assertIn('existing project',constraints)

    def test_unrelated_fabric_ui_request_is_not_reinterpreted_as_superpowers(self):
        c=MissionCompiler().compile('Crie uma demonstração com Microsoft Fabric UI')
        self.assertNotIn('Superpowers',' '.join(c.constraints))

    def test_all_explicit_method_aliases_are_disambiguated(self):
        for alias in ('skills Fabric','skills Frabic','SkillsFabric','Superpowers'):
            with self.subTest(alias=alias):
                c=MissionCompiler().compile('Atualize a versão utilizando '+alias)
                self.assertIn('Superpowers',' '.join(c.constraints))

    def run_fixture(self,source):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tests').mkdir();(root/'tests/__init__.py').write_text('')
            (root/'tests/test_check.py').write_text(source)
            return TargetedTestRunner(tmp).run_unittest(['tests.test_check'])

    def test_import_exit_zero_is_not_successful_test_evidence(self):
        r=self.run_fixture("import sys\nprint('PASS: expected UI found')\nsys.exit(0)\n")
        self.assertFalse(r.success,r.stdout+r.stderr)
        self.assertIn('unittest',r.stderr)

    def test_zero_discovered_tests_is_not_successful_test_evidence(self):
        r=self.run_fixture("def test_value():\n    assert True\n")
        self.assertFalse(r.success,r.stdout+r.stderr)

    def test_completed_unittest_case_remains_valid(self):
        r=self.run_fixture('import unittest\nclass T(unittest.TestCase):\n    def test_value(self): self.assertEqual(7,7)\n')
        self.assertTrue(r.success,r.stdout+r.stderr)

    def test_failed_unittest_remains_rejected(self):
        r=self.run_fixture('import unittest\nclass T(unittest.TestCase):\n    def test_value(self): self.assertEqual(7,8)\n')
        self.assertFalse(r.success)

if __name__=='__main__': unittest.main()
