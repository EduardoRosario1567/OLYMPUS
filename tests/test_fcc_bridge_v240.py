import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.provider_runtime import (
    _fcc_free_models,
    build_provider_registry,
    configured_free_routes,
    update_provider_preference,
)
from olympus.agent.output_compactor import compact_output
from olympus.routing.interfaces import ModelCapability, RoutingModelInfo
from olympus.routing.provider_fabric import OpenAICompatibleAdapter, ProviderConfig


class FccBridgeV240Tests(unittest.TestCase):
    def test_catalog_filter_never_treats_all_fcc_models_as_free(self):
        models = (
            "openai/gpt-5.5",
            "kimi/kimi-k2.5",
            "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
            "open_router/openrouter/free",
            "tokenrouter/moonshotai/kimi-k3-free",
            "lmstudio/qwen3.5-coder",
        )
        selected = _fcc_free_models(models)
        self.assertNotIn("openai/gpt-5.5", selected)
        self.assertNotIn("kimi/kimi-k2.5", selected)
        self.assertIn("nvidia_nim/nvidia/nemotron-3-super-120b-a12b", selected)
        self.assertIn("open_router/openrouter/free", selected)
        self.assertIn("lmstudio/qwen3.5-coder", selected)

    def test_exact_operator_allowlist_must_exist_in_live_catalog(self):
        with patch.dict(os.environ, {
            "OLYMPUS_FCC_FREE_MODELS": "approved/free,missing/free",
        }, clear=False):
            self.assertEqual(_fcc_free_models(("approved/free", "paid/model")), ("approved/free",))

    def test_fcc_is_optional_local_provider_without_bundled_secret(self):
        with patch.dict(os.environ, {"FCC_PROXY_TOKEN": "", "OLYMPUS_FCC_URL": "http://127.0.0.1:8082/v1"}, clear=False):
            registry = build_provider_registry(1)
        adapter = registry.adapter("fcc")
        self.assertTrue(adapter.config.enabled)
        self.assertEqual(adapter.config.base_url, "http://127.0.0.1:8082/v1")
        self.assertIsNone(adapter.config.api_key)

    def test_only_safe_fcc_models_enter_automatic_free_routes(self):
        class Adapter:
            def list_models(self):
                return [
                    RoutingModelInfo("openai/gpt-5.5", "fcc", [ModelCapability.CODIGO], True),
                    RoutingModelInfo("nvidia_nim/nvidia/nemotron", "fcc", [ModelCapability.CODIGO], True),
                ]

        class Registry:
            def adapter(self, provider):
                self.provider = provider
                return Adapter()

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "fcc",
        }, clear=True):
            update_provider_preference("omniroute", enabled=False, automatic=False)
            routes = configured_free_routes(Registry())
        self.assertEqual(tuple(route.id for route in routes), ("fcc::nvidia_nim/nvidia/nemotron",))

    def test_fcc_uses_responses_wire_protocol(self):
        adapter = OpenAICompatibleAdapter(ProviderConfig(
            "fcc", "http://127.0.0.1:8082/v1", wire_api="responses",
        ))
        captured = {}

        def request(method, path, payload=None, timeout=None):
            captured.update({"method": method, "path": path, "payload": payload})
            return 200, {
                "model": "nvidia_nim/model",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"type":"finish"}'}]}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

        adapter._request = request
        result = adapter.execute("nvidia_nim/model", "continue", max_tokens=256)
        self.assertTrue(result.success)
        self.assertEqual(captured["path"], "/responses")
        self.assertEqual(captured["payload"]["max_output_tokens"], 256)
        self.assertNotIn("messages", captured["payload"])
        self.assertIn('"finish"', result.output)

    def test_long_output_is_compacted_without_losing_diagnostic(self):
        raw = "header\n" + "progress\n" * 500 + "AssertionError: expected 2 actual 3\n" + "tail\n" * 50
        result = compact_output(raw, max_chars=1200, max_lines=40)
        self.assertLessEqual(result.compacted_chars, 1200)
        self.assertIn("AssertionError", result.text)
        self.assertIn("header", result.text)
        self.assertGreater(result.omitted_lines, 0)

    def test_frontend_and_launcher_explain_optional_gateway(self):
        from tests.frontend_contract import check_browser
        check_browser('connections')
        from tests.launcher_contract import launch
        result = launch()
        self.assertEqual(result['code'], 0, result['output'])
        self.assertNotIn('fcc-server', result['trace'])


if __name__ == "__main__":
    unittest.main()
