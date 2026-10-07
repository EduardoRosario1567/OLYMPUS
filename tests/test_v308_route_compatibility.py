import unittest
from unittest.mock import patch

from app.core import provider_runtime as runtime
from olympus.agent.multibrain_registry import AgentModelRoute


SAFETY = AgentModelRoute('openrouter/nvidia/nemotron-3.5-content-safety:free', 'Safety', 'openrouter', 1000)
JEV = AgentModelRoute('opencode_zen::jev-1.13-free', 'Jev', 'opencode_zen', 900)
OLLAMA = AgentModelRoute('ollama_cloud::gpt-oss:120b', 'Ollama', 'ollama_cloud', 800)
GROQ = AgentModelRoute('groq::qwen/qwen3.8-27b', 'Groq', 'groq', 700)
BATCH = AgentModelRoute(
    'openrouter::google/gemini-3.8-flash:batch',
    'Gemini batch',
    'openrouter',
    750,
)
EXO = AgentModelRoute(
    'opencode_zen::exo-free',
    'Exo Free',
    'opencode_zen',
    740,
)
ZEN_NEMOTRON = AgentModelRoute(
    'opencode_zen::nemotron-3.5-lightning-free',
    'Nemotron 3.5 Lightning Free',
    'opencode_zen',
    730,
)


class RouteCompatibilityTests(unittest.TestCase):
    def routes(self, candidates, limit=6):
        with patch.object(runtime, 'configured_free_routes', return_value=candidates), \
             patch.object(runtime, 'capacity_filter_routes', side_effect=lambda items: tuple(items)):
            return runtime.configured_mission_routes(policy_override={
                'mode':'free_first', 'free_attempt_limit':limit,
                'paid_fallback_authorized':False, 'paid_spend_cap_usd':0})

    def test_specialist_routes_do_not_consume_free_attempts(self):
        self.assertEqual(self.routes((SAFETY, JEV, OLLAMA, GROQ), limit=2), (OLLAMA, GROQ))

    def test_only_incompatible_routes_yield_no_candidates(self):
        self.assertEqual(self.routes((SAFETY, JEV)), ())

    def test_batch_route_is_not_used_by_interactive_agent(self):
        self.assertEqual(
            self.routes((BATCH, GROQ)),
            (GROQ,),
        )

    def test_opencode_exo_free_is_excluded_without_disabling_zen(self):
        self.assertEqual(
            self.routes((EXO, ZEN_NEMOTRON, GROQ), limit=3),
            (ZEN_NEMOTRON, GROQ),
        )

    def test_general_nemotron_and_dynamic_router_are_kept(self):
        lightning = AgentModelRoute('openrouter/nvidia/nemotron-3.5-lightning:free', 'Lightning', 'openrouter', 500)
        dynamic = AgentModelRoute('openrouter/openrouter/free', 'Dynamic', 'openrouter', 400)
        self.assertEqual(self.routes((lightning, dynamic)), (lightning, dynamic))


if __name__ == '__main__': unittest.main()
