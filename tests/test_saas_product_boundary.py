from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SaaSProductBoundaryTests(unittest.TestCase):
    def test_legacy_global_api_is_opt_in(self):
        main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertIn('if os.environ.get("OLYMPUS_ENABLE_LEGACY_API") == "1"', main)
        conditional = main.split('if os.environ.get("OLYMPUS_ENABLE_LEGACY_API") == "1":', 1)[1]
        for router in ("dashboard", "projects", "executions", "logs", "missions"):
            self.assertIn("app.include_router(%s.router)" % router, conditional)

    def test_production_configuration_fails_closed(self):
        security = (ROOT / "backend/app/core/security.py").read_text(encoding="utf-8")
        main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertIn("validar_configuracao_producao", security)
        self.assertIn("SECRET_KEY == _DEVELOPMENT_SECRET", security)
        self.assertIn('"*" in origens', main)

    def test_product_routes_use_server_side_permissions(self):
        projects = (ROOT / "backend/app/api/cloud_projects.py").read_text(encoding="utf-8")
        runtime = (ROOT / "backend/app/api/cloud_runtime.py").read_text(encoding="utf-8")
        github = (ROOT / "backend/app/api/github.py").read_text(encoding="utf-8")
        railway = (ROOT / "backend/app/api/railway.py").read_text(encoding="utf-8")
        self.assertIn('identidade_com_permissao("projects.read")', projects)
        self.assertIn('identidade_com_permissao("projects.write")', projects)
        self.assertIn('identidade_com_permissao("missions.run")', runtime)
        self.assertIn('identidade_com_permissao("deployments.manage")', github)
        self.assertIn('identidade_com_permissao("deployments.manage")', railway)
        for source in (projects, runtime, github, railway):
            self.assertNotIn("Depends(identidade_autenticada)", source)

    def test_billing_has_no_unverified_public_mutation_route(self):
        api = (ROOT / "backend/app/api/saas.py").read_text(encoding="utf-8")
        billing = (ROOT / "olympus/saas/billing.py").read_text(encoding="utf-8")
        self.assertNotIn("billing", api.lower())
        self.assertIn("verify_and_parse", billing)
        self.assertIn("apply_verified_billing_event", billing)


if __name__ == "__main__":
    unittest.main()
