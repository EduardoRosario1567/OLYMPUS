import unittest
from olympus.agent.control_plane import AgentControlPlane
from olympus.agent.loop import AgentLoopResult
from olympus.agent.state import AgentState, AgentStatus

FREE = 'openrouter/openrouter/free'
OLD = 'ollama_cloud::gpt-oss:120b'
OTHER = 'groq::qwen/qwen3.8-27b'

class Selector:
    def __init__(self, models): self.models = models
    def select_candidates(self, task): return self.models

class ResumeFallbackTests(unittest.TestCase):
    def run_chain(self, candidates, previous, failures, completed=None):
        initial = AgentState('task', files_modified=('src/existing.py',), tests_run=('tests.test_existing',))
        events = []
        states = []
        class Loop:
            def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
                states.append(initial_state)
                state = initial_state.resume_for_model(selected_model)
                if selected_model == completed:
                    return AgentLoopResult(state.transition(AgentStatus.COMPLETED), ())
                error = failures.get(selected_model, 'malformed_response: model returned no textual action')
                return AgentLoopResult(state.transition(AgentStatus.BLOCKED, errors=state.errors+(error,), metadata={'failure_kind':'technical'}), ())
        plane = AgentControlPlane('.', object(), Selector(candidates), lambda r,m:m, lambda root,p:Loop(), events.append)
        result = plane.run_attempts('task', initial_state=initial, previously_attempted=previous)
        for state in states:
            self.assertEqual(state.files_modified, initial.files_modified)
            self.assertEqual(state.tests_run, initial.tests_run)
        return result, events

    def test_new_dynamic_route_failure_hands_off_to_previously_used_eligible_model(self):
        result, events = self.run_chain((OLD,OTHER,FREE), (OLD,OTHER), {}, OLD)
        self.assertEqual(result.models_attempted, (FREE,OLD))
        self.assertEqual(result.final.state.status, AgentStatus.COMPLETED)
        handoff = next(e for e in events if e['event']=='model_failover')
        self.assertEqual(handoff['next_model'], OLD)
        self.assertTrue(handoff['cross_provider'])

    def test_provider_auth_failure_does_not_retry_prior_model_from_same_provider(self):
        same = 'openrouter/another/free'
        result, events = self.run_chain((same,OLD,FREE), (same,OLD), {FREE:'authentication_error: denied'}, OLD)
        self.assertEqual(result.models_attempted, (FREE,OLD))
        self.assertTrue(next(e for e in events if e['event']=='model_failover')['provider_blocked'])

    def test_previous_routes_outside_current_candidates_are_not_restored(self):
        result, events = self.run_chain((FREE,), (OLD,OTHER,'paid::model','opencode_zen::jev-1.13-free'), {})
        self.assertEqual(result.models_attempted, (FREE,FREE,FREE))
        self.assertEqual(result.final.state.status, AgentStatus.BLOCKED)

    def test_exhaustion_is_bounded_without_duplicate_fixed_routes(self):
        result, events = self.run_chain((OLD,OTHER,FREE), (OLD,OTHER), {})
        self.assertEqual(result.models_attempted, (FREE,OLD,OTHER))
        self.assertIsNone([e for e in events if e['event']=='model_failover'][-1]['next_model'])

if __name__ == '__main__': unittest.main()
