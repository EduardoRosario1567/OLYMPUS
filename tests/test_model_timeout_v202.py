import unittest
from pathlib import Path


class TestModelTimeoutV202(unittest.TestCase):
    def test_cloud_and_legacy_runtime_use_free_model_budget(self):
        import os
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.api import cloud_runtime, missions
        for override, cloud_budget, legacy_budget in ((None,90,30),("73",73,73)):
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OLYMPUS_MODEL_TIMEOUT", None)
                if override: os.environ["OLYMPUS_MODEL_TIMEOUT"] = override
                with patch.object(cloud_runtime, "build_mission_routing", return_value=(object(),object())) as routing, patch.object(cloud_runtime, "AutonomousDeveloper"):
                    cloud_runtime._runner_factory(directory, lambda e: None)
                    self.assertEqual(routing.call_args.args[0], cloud_budget)
                record = {"task":"create helper", "_max_iterations":2, "models":[], "events":[]}
                report = SimpleNamespace(steps=[],success=True,status="completed",error=None)
                with patch.dict(missions._MISSIONS, {"qa-budget":record}), patch.object(missions, "OmniRouteAdapter") as adapter, patch.object(missions,"AutonomousPatchRunner") as runner:
                    runner.return_value.run.return_value = report
                    missions._run_mission("qa-budget")
                    self.assertEqual(adapter.call_args.kwargs["timeout_seconds"], legacy_budget)
        self.assertEqual(cloud_runtime._adaptive_model_timeout("crie um site"),90)
        self.assertEqual(cloud_runtime._adaptive_model_timeout("corrija Python"),60)

    def test_launcher_upgrades_existing_install_without_overwriting_env(self):
        from tests.launcher_contract import launch
        for override, expected in ((None,90),(73,73)):
            result = launch(timeout=override)
            self.assertEqual(result['code'], 0, result['output'])
            self.assertEqual(result['env'], 'SYNTHETIC_SECRET=preserved\n')
            self.assertIn('timeout='+str(expected), result['trace'])
            self.assertFalse(result['stale_cache_exists'])
            self.assertNotIn('pip install', result['trace'])
            self.assertNotIn('npm install', result['trace'])

    def test_health_exposes_release_version_for_safe_restart(self):
        import json
        from app.main import app
        from fastapi.testclient import TestClient
        metadata = json.loads((Path(__file__).resolve().parents[1] / "frontend/public/olympus-version.json").read_text())
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert app.version == metadata["version"]
        assert response.json()["version"] == metadata["version"]
        assert response.json()["build"] == metadata["build"]

    def test_launcher_replaces_only_identifiable_stale_olympus_services(self):
        from tests.launcher_contract import launch
        for scenario in ({'foreign':True},{'reused':True}):
            result = launch(**scenario)
            self.assertNotEqual(result['code'],0)
            self.assertNotIn('kill -KILL',result['trace'])
            if scenario.get('foreign'): self.assertNotIn('kill',result['trace'])

    def test_example_documents_timeout(self):
        example = Path("backend/.env.example").read_text(encoding="utf-8")
        self.assertIn("OLYMPUS_MODEL_TIMEOUT=30", example)
        self.assertIn("OLYMPUS_PROVIDER_TEST_TIMEOUT=60", example)

    def test_provider_generation_check_does_not_reuse_liveness_timeout(self):
        providers = Path("backend/app/api/providers.py").read_text(encoding="utf-8")
        self.assertIn('OLYMPUS_PROVIDER_TEST_TIMEOUT", "60"', providers)
        self.assertIn("build_provider_registry(timeout_seconds=test_timeout)", providers)


if __name__ == "__main__":
    unittest.main()
