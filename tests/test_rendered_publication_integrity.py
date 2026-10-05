"""Executable acceptance tests cannot leave a stale rendered approval behind."""
from pathlib import Path
import time
import sys
from types import SimpleNamespace

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.agent.acceptance import compile_contract
from olympus.agent.state import AgentState
from olympus.cloud.runtime import CloudRuntime
from tests.test_browser_delivery_gate import workspace


def mutation_test(root):
    (root/'tests').mkdir(exist_ok=True)
    (root/'tests/__init__.py').write_text('# Project test package\n')
    (root/'tests/test_mutation.py').write_text('''import unittest
from pathlib import Path
class Mutation(unittest.TestCase):
    def test_writes_output(self):
        page=Path(__file__).resolve().parents[1]/'app/index.html'
        text=page.read_text()
        if 'afterTestsBrokenInitializer' not in text:
            page.write_text(text.replace('</body>','<script>afterTestsBrokenInitializer()</script></body>'))
        self.assertTrue(page.is_file())
''')


def test_publication_uses_page_after_project_tests_execute(tmp_path):
    class Runner:
        def __init__(self,root): self.root=Path(root)
        def run(self,task,**kwargs):
            workspace(self.root)
            mutation_test(self.root)
            return SimpleNamespace(status='completed',error=None,
                files_modified=('app/index.html','docs/delivery-concept.md','tests/__init__.py','tests/test_mutation.py'),
                tests_run=('tests.test_mutation',))
    runtime=CloudRuntime(str(tmp_path/'runtime'),lambda root,telemetry:Runner(root),max_workers=1)
    try:
        rec=runtime.submit('rosales','Crie uma landing page HTML para Rosales Café.')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            rec=runtime.get(rec.execution_id)
            if rec.status in {'completed','failed','blocked'}: break
            time.sleep(.02)
        assert rec.status=='failed', 'a passing project test published JavaScript that broke after the capture'
        event=next(item for item in runtime.events(rec.execution_id) if item['event']=='completion_rejected')
        assert any('afterTestsBrokenInitializer' in item for item in event['errors'])
        assert event['delivery_review']['browser']=='failed'
        assert not any(item['event']=='result_published' for item in runtime.events(rec.execution_id))
    finally: runtime.close()


def test_loop_checks_rendered_delivery_after_acceptance_side_effects(tmp_path):
    contract=compile_contract('Crie uma landing page HTML para Rosales Café e execute os testes.',tmp_path,
        test_command=[sys.executable,'-m','unittest','tests.test_mutation','-v'])
    contract.prepare()
    task=workspace(tmp_path)
    mutation_test(tmp_path)
    class Planner:
        def next_action(self,*args): return AgentAction(ActionType.FINISH,payload='ready')
    initial=AgentState(task=task,max_iterations=2,files_modified=('app/index.html','docs/delivery-concept.md'))
    result=AgentLoop(str(tmp_path),Planner(),acceptance_contract=contract).run(task,max_iterations=2,initial_state=initial)
    assert result.state.status.value!='completed', 'acceptance changed the rendered artifact after approval'
    assert any('afterTestsBrokenInitializer' in item for item in result.state.errors)
    assert result.state.metadata['delivery_review']['browser']=='failed'
