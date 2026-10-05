import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ProductOnboardingV2714Tests(unittest.TestCase):
    def test_omniroute_key_can_be_managed_by_olympus(self):
        from app.core.provider_runtime import update_provider_secret, remove_provider_secret
        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            with patch.dict(os.environ, {"OLYMPUS_CREDENTIALS_PATH": str(env_path)}, clear=False):
                update_provider_secret("omniroute", "test-secret")
                text = env_path.read_text(encoding="utf-8")
                self.assertIn("OLYMPUS_OMNIROUTE_API_KEY=test-secret", text)
                self.assertEqual(os.environ.get("OLYMPUS_OMNIROUTE_API_KEY"), "test-secret")
                remove_provider_secret("omniroute")
                self.assertNotIn("OLYMPUS_OMNIROUTE_API_KEY=", env_path.read_text(encoding="utf-8"))

    def test_ollama_cloud_key_can_be_managed_by_olympus(self):
        from app.core.provider_runtime import update_provider_secret, remove_provider_secret
        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            with patch.dict(os.environ, {"OLYMPUS_CREDENTIALS_PATH": str(env_path)}, clear=False):
                update_provider_secret("ollama_cloud", "ollama-secret")
                text = env_path.read_text(encoding="utf-8")
                self.assertIn("OLLAMA_API_KEY=ollama-secret", text)
                remove_provider_secret("ollama_cloud")
                self.assertNotIn("OLLAMA_API_KEY=", env_path.read_text(encoding="utf-8"))

    def test_ollama_local_has_no_secret_field(self):
        from app.core.provider_runtime import update_provider_secret
        with self.assertRaises(KeyError):
            update_provider_secret("ollama", "should-not-be-used")

    def test_default_route_still_starts_with_conding_free(self):
        from app.core.provider_runtime import configured_free_routes
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "",
            "GROQ_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OLLAMA_API_KEY": "",
        }, clear=False):
            routes = configured_free_routes(None)
        self.assertTrue(routes)
        self.assertEqual(routes[0].id, "Conding-free")

    def test_ollama_cloud_direct_is_not_automatic_by_default(self):
        from app.core.provider_runtime import configured_free_routes
        with patch.dict(os.environ, {"OLLAMA_API_KEY": "configured"}, clear=False):
            routes = configured_free_routes(None)
        providers = [route.provider for route in routes]
        self.assertNotIn("ollama_cloud", providers)


if __name__ == "__main__":
    unittest.main()
