import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.provider_runtime import SpendGuardRoutingAdapter, configured_mission_routes, remove_provider_secret, routing_policy, update_provider_preference, update_provider_secret, update_routing_policy
from olympus.routing.interfaces import RoutingExecutionResult


class RoutingPolicyV230Tests(unittest.TestCase):
    def test_free_chain_is_bounded_and_diversified(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory,"settings.json")),
            "GROQ_API_KEY":"key", "GEMINI_API_KEY":"key",
            "OLYMPUS_FREE_FALLBACK_PROVIDERS":"groq,gemini",
        }, clear=True):
            update_provider_preference("gemini",enabled=True,automatic=True,priority=20)
            routes=configured_mission_routes(policy_override={"free_attempt_limit":3})
        self.assertLessEqual(len(routes),3)
        self.assertEqual(len({route.provider for route in routes}),3)

    def test_paid_routes_require_authorization_and_positive_cap(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory,"settings.json")),
            "OPENAI_API_KEY":"key", "OLYMPUS_FREE_FALLBACK_PROVIDERS":"",
        }, clear=True):
            update_provider_preference("omniroute",enabled=False,automatic=False)
            update_provider_preference("openai",enabled=True,automatic=True)
            self.assertEqual(configured_mission_routes(policy_override={"mode":"protected"}),())
            routes=configured_mission_routes(policy_override={
                "mode":"protected", "paid_fallback_authorized":True,
                "paid_spend_cap_usd":1.0, "paid_attempt_limit":1,
            })
        self.assertEqual(len(routes),1)
        self.assertEqual(routes[0].tier,"paid")

    def test_opencode_zen_free_chain_excludes_paid_models(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
            "OPENCODE_API_KEY": "zen-key",
            "OLYMPUS_OPENCODE_ZEN_MODELS": "mimo-v2.6-flash-free,gpt-5.4-mini,nemotron-3.5-lightning-free",
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "opencode_zen",
        }, clear=True):
            update_provider_preference("omniroute", enabled=False, automatic=False)
            routes = configured_mission_routes(policy_override={"free_attempt_limit": 8})
        ids = tuple(route.id for route in routes)
        self.assertIn("opencode_zen::mimo-v2.6-flash-free", ids)
        self.assertIn("opencode_zen::nemotron-3.5-lightning-free", ids)
        self.assertNotIn("opencode_zen::gpt-5.4-mini", ids)

    def test_opencode_zen_paid_route_requires_authorization(self):
        class ZenRegistry:
            class Adapter:
                def list_models(self):
                    from olympus.routing.interfaces import RoutingModelInfo, ModelCapability
                    return [
                        RoutingModelInfo("mimo-v2.6-flash-free", "opencode_zen", [ModelCapability.CODIGO], True),
                        RoutingModelInfo("gpt-5.4-mini", "opencode_zen", [ModelCapability.CODIGO], True),
                    ]
            def adapter(self, provider):
                return self.Adapter()

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
            "OPENCODE_API_KEY": "zen-key",
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "",
            "OLYMPUS_OPENCODE_ZEN_MODELS": "gpt-5.4-mini",
        }, clear=True):
            update_provider_preference("omniroute", enabled=False, automatic=False)
            update_provider_preference("opencode_zen", enabled=True, automatic=True)
            free_only = configured_mission_routes(ZenRegistry(), policy_override={"mode": "protected"})
            paid = configured_mission_routes(ZenRegistry(), policy_override={
                "mode": "protected", "paid_fallback_authorized": True,
                "paid_spend_cap_usd": 1.0, "paid_attempt_limit": 1,
            })
        self.assertEqual(free_only, ())
        self.assertEqual(tuple(route.id for route in paid), ("opencode_zen::gpt-5.4-mini",))

    def test_saved_paid_policy_cannot_be_open_ended(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory,"settings.json")),
        }, clear=True):
            with self.assertRaises(ValueError):
                update_routing_policy(mode="protected",paid_fallback_authorized=True,paid_spend_cap_usd=0)

    def test_provider_secret_is_persisted_without_returning_the_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "provider-keys.env")
            with patch.dict(os.environ, {"OLYMPUS_CREDENTIALS_PATH": str(path)}, clear=False):
                update_provider_secret("opencode_zen", "zen-secret")
                self.assertEqual(os.environ["OPENCODE_API_KEY"], "zen-secret")
                self.assertIn("OPENCODE_API_KEY=zen-secret", path.read_text(encoding="utf-8"))
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                remove_provider_secret("opencode_zen")
                self.assertNotIn("OPENCODE_API_KEY=", path.read_text(encoding="utf-8"))

    def test_spend_guard_blocks_before_call_and_accounts_for_usage(self):
        class Adapter:
            def __init__(self): self.calls=0
            def execute(self,model_id,prompt,**kwargs):
                self.calls += 1
                return RoutingExecutionResult(model_id,model_id,"openai","ok",1,0,True,metadata={"usage":{"prompt_tokens":100,"completion_tokens":50}})
        blocked_adapter=Adapter()
        blocked=SpendGuardRoutingAdapter(blocked_adapter,0.000001).execute("openai::gpt","hello",max_tokens=100)
        self.assertFalse(blocked.success)
        self.assertEqual(blocked_adapter.calls,0)
        allowed_adapter=Adapter()
        allowed=SpendGuardRoutingAdapter(allowed_adapter,1).execute("openai::gpt","hello",max_tokens=100)
        self.assertTrue(allowed.success)
        self.assertEqual(allowed_adapter.calls,1)
        self.assertGreater(allowed.metadata["estimated_cost_usd"],0)


if __name__ == "__main__": unittest.main()
