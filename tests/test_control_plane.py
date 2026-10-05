import unittest
from olympus.agent.control_plane import AgentControlPlane
from olympus.agent.loop import AgentLoopResult
from olympus.agent.state import AgentState, AgentStatus

class Selector:
    def select_candidates(self, task): return ('model/a','model/b')
class Loop:
    def __init__(self, model): self.model=model
    def run(self, task, selected_model=None, max_iterations=12):
        state=AgentState(task,selected_model=selected_model)
        if selected_model=='model/a':
            state=state.transition(AgentStatus.BLOCKED,errors=('timeout: timed out',),metadata={'failure_kind':'technical'})
        else: state=state.transition(AgentStatus.COMPLETED)
        return AgentLoopResult(state,())
class LogicalLoop(Loop):
    def run(self, task, selected_model=None, max_iterations=12):
        state=AgentState(task,selected_model=selected_model).transition(AgentStatus.FAILED,errors=('invalid task',),metadata={'failure_kind':'logical'})
        return AgentLoopResult(state,())
class FreeSelector:
    def select_candidates(self, task): return ('openrouter/openrouter/free',)
class FlakyFreeLoop:
    calls=0
    def __init__(self, model): self.model=model
    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        type(self).calls += 1
        if type(self).calls == 1:
            state=AgentState(task,selected_model=selected_model,max_iterations=max_iterations).next_iteration()
            state=state.transition(AgentStatus.BLOCKED,files_modified=('app/index.html',),errors=('Timeout: provider timed out',),metadata={'failure_kind':'technical'})
            return AgentLoopResult(state,())
        assert initial_state is not None
        assert initial_state.files_modified == ('app/index.html',)
        return AgentLoopResult(initial_state.resume_for_model(selected_model).transition(AgentStatus.COMPLETED),())
class TestControlPlane(unittest.TestCase):
    def build(self, loop_cls=Loop, events=None):
        return AgentControlPlane('.',object(),Selector(),lambda r,m:m,lambda root,p:loop_cls(p),events.append if events is not None else None)
    def test_technical_failure_fails_over(self):
        events=[]; result=self.build(events=events).run_attempts('task')
        self.assertEqual(result.models_attempted,('model/a','model/b'))
        self.assertEqual(result.final.state.status,AgentStatus.COMPLETED)
        self.assertTrue(any(e['event']=='model_failover' for e in events))
    def test_logical_failure_does_not_switch_model(self):
        result=self.build(LogicalLoop).run_attempts('task')
        self.assertEqual(result.models_attempted,('model/a',))
        self.assertEqual(result.final.state.status,AgentStatus.FAILED)

    def test_resumed_chain_starts_with_first_model_not_already_attempted(self):
        events=[]
        result=self.build(events=events).run_attempts(
            'task', previously_attempted=('model/a',)
        )
        self.assertEqual(result.models_attempted,('model/b',))
    def test_single_dynamic_free_route_retries_another_underlying_model(self):
        FlakyFreeLoop.calls=0
        events=[]
        plane=AgentControlPlane('.',object(),FreeSelector(),lambda r,m:m,lambda root,p:FlakyFreeLoop(p),events.append)
        result=plane.run_attempts('task')
        self.assertEqual(result.models_attempted,('openrouter/openrouter/free','openrouter/openrouter/free'))
        self.assertEqual(result.final.state.status,AgentStatus.COMPLETED)
        failover=next(event for event in events if event['event']=='model_failover')
        self.assertTrue(failover['dynamic_route_retry'])
if __name__=='__main__': unittest.main()
