import unittest
from olympus.agent.control_plane import AgentControlPlane
from olympus.agent.loop import AgentLoopResult
from olympus.agent.recovery import FailureKind, classify_failure
from olympus.agent.state import AgentState, AgentStatus

class Selector:
    def select_candidates(self, task):
        return ('model/a','model/b')

class StatefulLoop:
    def __init__(self, model): self.model=model
    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        if selected_model == 'model/a':
            state=AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
            state=state.next_iteration()
            state=state.transition(AgentStatus.BLOCKED,
                files_modified=('olympus/example.py',), tests_run=('tests.test_example',),
                errors=('429 rate limit',), metadata={'failure_kind':'technical'})
            return AgentLoopResult(state,({'model':selected_model},))
        self.assert_checkpoint(initial_state)
        state=initial_state.resume_for_model(selected_model).transition(AgentStatus.COMPLETED)
        return AgentLoopResult(state,({'model':selected_model},))
    def assert_checkpoint(self,state):
        assert state is not None
        assert state.files_modified == ('olympus/example.py',)
        assert state.tests_run == ('tests.test_example',)
        assert state.iteration == 1

class LogicalLoop(StatefulLoop):
    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        state=AgentState(task,selected_model=selected_model).transition(
            AgentStatus.FAILED,errors=('invalid requirement',),metadata={'failure_kind':'logical'})
        return AgentLoopResult(state,())

class TestRecoveryFailover042(unittest.TestCase):
    def build(self,loop_cls,events):
        return AgentControlPlane('.',object(),Selector(),lambda r,m:m,
            lambda root,model: loop_cls(model),events.append)
    def test_timeout_and_provider_errors_are_technical(self):
        for value in ('timeout: timed out','429 rate limit','provider_error','connection refused','temporarily unavailable'):
            self.assertEqual(classify_failure(value),FailureKind.TECHNICAL)
    def test_failover_preserves_progress(self):
        events=[]
        result=self.build(StatefulLoop,events).run_attempts('task')
        self.assertEqual(result.models_attempted,('model/a','model/b'))
        self.assertEqual(result.final.state.status,AgentStatus.COMPLETED)
        self.assertEqual(result.final.state.files_modified,('olympus/example.py',))
        self.assertEqual(result.final.state.tests_run,('tests.test_example',))
        self.assertEqual(
            result.final.state.metadata['model_handoffs'][-1]['from_model'],
            'model/a',
        )
        self.assertEqual(
            result.final.state.metadata['model_handoffs'][-1]['to_model'],
            'model/b',
        )
        self.assertTrue(any(e['event']=='model_resume' for e in events))
    def test_logical_failure_never_fails_over(self):
        events=[]
        result=self.build(LogicalLoop,events).run_attempts('task')
        self.assertEqual(result.models_attempted,('model/a',))
        self.assertEqual(result.final.state.status,AgentStatus.FAILED)
        self.assertFalse(any(e['event']=='model_failover' for e in events))
    def test_budget_is_not_technical(self):
        self.assertEqual(classify_failure('iteration budget exhausted'),FailureKind.LOGICAL)

if __name__=='__main__': unittest.main()
