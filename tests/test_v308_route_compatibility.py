import unittest
from unittest.mock import patch

from app.core import provider_runtime as runtime
from olympus.agent.multibrain_registry import AgentModelRoute


SAFETY = AgentModelRoute('openrouter/nvidia/nemotron-3.5-content-safety:free', 'Safety', 'openrouter', 1000)
JEV = AgentModelRoute('opencode_zen::jev-1.13-free', 'Jev', 'opencode_zen', 900)
OLLAMA = AgentModelRoute('ollama_cloud::gpt-oss:120b', 'Ollama', 'ollama_cloud', 800)
GROQ = AgentModelRoute('groq::qwen/qwen3.8-27b', 'Groq', 'groq', 700)


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

    def test_general_nemotron_and_dynamic_router_are_kept(self):
        lightning = AgentModelRoute('openrouter/nvidia/nemotron-3.5-lightning:free', 'Lightning', 'openrouter', 500)
        dynamic = AgentModelRoute('openrouter/openrouter/free', 'Dynamic', 'openrouter', 400)
        self.assertEqual(self.routes((lightning, dynamic)), (lightning, dynamic))


if __name__ == '__main__': unittest.main()
