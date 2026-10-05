import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class ConnectionsHubV220Tests(unittest.TestCase):
    def test_preferences_are_atomic_secret_free_and_drive_registry_order(self):
        from app.core.provider_runtime import build_provider_registry, update_provider_preference

        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory, "provider-settings.json")
            environment = {
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(settings),
                "GROQ_API_KEY": "private-key-never-persisted",
            }
            with patch.dict(os.environ, environment, clear=True):
                update_provider_preference("groq", enabled=True, priority=5)
                registry = build_provider_registry()

            content = settings.read_text(encoding="utf-8")
            self.assertNotIn("private-key-never-persisted", content)
            self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
            self.assertEqual(registry.ids()[0], "groq")
            self.assertTrue(registry.adapter("groq").config.enabled)
            self.assertEqual(json.loads(content)["providers"]["groq"], {"enabled": True, "priority": 5})

    def test_provider_can_be_disabled_without_deleting_credential(self):
        from app.core.provider_runtime import build_provider_registry, configured_free_routes, update_provider_preference

        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
                "GROQ_API_KEY": "configured-secret",
                "OLYMPUS_FREE_FALLBACK_PROVIDERS": "groq",
            }
            with patch.dict(os.environ, environment, clear=True):
                update_provider_preference("groq", enabled=False)
                registry = build_provider_registry()
                routes = configured_free_routes()
            self.assertFalse(registry.adapter("groq").config.enabled)
            self.assertFalse(any(route.id.startswith("groq::") for route in routes))

    def test_direct_openrouter_key_adds_independent_free_route(self):
        from app.core.provider_runtime import configured_free_routes

        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
                "OPENROUTER_API_KEY": "configured-secret",
                "OLYMPUS_FREE_FALLBACK_PROVIDERS": "openrouter",
            }
            with patch.dict(os.environ, environment, clear=True):
                route_ids = tuple(route.id for route in configured_free_routes())
        self.assertEqual(route_ids, (
            "Conding-free",
            "openrouter/openrouter/free",
            "openrouter::openrouter/free",
        ))

    def test_catalog_and_control_endpoints_exist(self):
        try:
            from backend.app.api import providers
        except ImportError:
            self.skipTest("FastAPI is an optional HTTP-runtime dependency")
        contracts = {(route.path, next(iter(route.methods or ()))) for route in providers.router.routes}
        paths = {path for path, _method in contracts}
        self.assertIn("/providers/catalog", paths)
        self.assertIn("/providers/{provider_id}", paths)
        self.assertIn("/providers/{provider_id}/test", paths)

    def test_connection_test_performs_a_minimal_real_generation(self):
        source = (ROOT / "backend/app/api/providers.py").read_text(encoding="utf-8")
        self.assertIn(".execute(", source)
        self.assertIn("max_tokens=256", source)
        self.assertIn("normalize_action_text", source)
        self.assertIn("action.type == ActionType.FINISH", source)
        self.assertIn("action_protocol_invalid", source)
        self.assertIn('"inference_ready"', source)
        self.assertIn("Protocolo Olympus confirmado", source)

    def test_frontend_exposes_product_facing_connections_center(self):
        from tests.frontend_contract import check_browser
        check_browser('connections')

    def test_configurator_supports_every_direct_cloud_provider(self):
        source = (ROOT / "scripts/configure_ai_providers.py").read_text(encoding="utf-8")
        for key in (
            "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
            "OPENAI_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY",
        ):
            self.assertIn(key, source)

    def test_application_start_is_not_blocked_by_optional_omniroute(self):
        from tests.launcher_contract import launch
        result = launch()
        self.assertEqual(result['code'], 0, result['output'])
        self.assertIn('uvicorn', result['trace'])
        self.assertIn('npm run dev', result['trace'])


if __name__ == "__main__":
    unittest.main()
