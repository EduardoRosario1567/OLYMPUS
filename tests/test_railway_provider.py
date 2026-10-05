import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.cloud.deployment import (
    DeploymentCoordinator,
    DeploymentPolicyError,
    DeploymentRequest,
    MemorySecretVault,
    SQLiteDeploymentRecordStore,
    build_deployment_artifact,
)
from olympus.cloud.railway_provider import (
    RAILWAY_GRAPHQL_URL,
    RailwayApi,
    RailwayApiError,
    RailwayBinding,
    RailwayBindingStore,
    RailwayIntegrationService,
    RailwayProvider,
    SQLiteRailwayDeploymentBindingStore,
)


TOKEN = "railway-token-" + "x" * 40
REVISION = "a" * 40


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit):
        return self.body


class FakeRailwayApi:
    def __init__(self, token=TOKEN):
        self.token = token
        self.variables = None
        self.created_domain = None
        self.rollback_target = None
        self.revision = REVISION

    def account(self):
        return {"id": "account-1", "name": "Conta", "email": "private@example.com"}

    def service(self, service_id):
        return {"id": service_id, "name": "web", "projectId": "railway-project"}

    def service_instance(self, service_id, environment_id):
        return {"id": "instance", "serviceName": service_id, "latestDeployment": None}

    def upsert_variables(self, project_id, environment_id, service_id, variables):
        self.variables = dict(variables)

    def deploy_service(self, service_id, environment_id):
        return "deployment-new"

    def deployment(self, deployment_id):
        return {"id": deployment_id, "status": "SUCCESS", "staticUrl": "app.up.railway.app",
                "meta": {"commitHash": self.revision}, "canRollback": True}

    def rollback(self, target_deployment_id):
        self.rollback_target = target_deployment_id
        return {"id": "deployment-rollback", "status": "QUEUED", "staticUrl": "app.up.railway.app"}

    def create_domain(self, project_id, environment_id, service_id, domain):
        self.created_domain = domain
        return {"id": "domain-1", "domain": domain, "status": {"dnsRecords": [
            {"hostlabel": "app", "requiredValue": "target.railway.app", "status": "PENDING"}
        ]}}


class RailwayApiTests(unittest.TestCase):
    def test_uses_fixed_origin_bearer_and_graphql_body(self):
        response = FakeResponse(b'{"data":{"me":{"id":"account-1"}}}')
        with patch("olympus.cloud.railway_provider.urlopen", return_value=response) as opened:
            result = RailwayApi(TOKEN).account()
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, RAILWAY_GRAPHQL_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertIn("query", json.loads(request.data))
        self.assertEqual(result["id"], "account-1")

    def test_graphql_errors_are_sanitized(self):
        response = FakeResponse(b'{"errors":[{"message":"secret railway-token-value"}]}')
        with patch("olympus.cloud.railway_provider.urlopen", return_value=response):
            with self.assertRaises(RailwayApiError) as caught:
                RailwayApi(TOKEN).account()
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_rejects_header_injection(self):
        with self.assertRaises(ValueError):
            RailwayApi(TOKEN + "\nInjected: yes")


class RailwayBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name, "railway.json")

    def tearDown(self):
        self.temporary.cleanup()

    def test_binding_is_durable_and_contains_no_token(self):
        store = RailwayBindingStore(self.path)
        binding = RailwayBinding("tenant", "project", "railway-project", "service", "environment", "owner/repo", 1.0, 2.0)
        store.put(binding)
        self.assertEqual(RailwayBindingStore(self.path).get("project", "tenant"), binding)
        self.assertNotIn(TOKEN, self.path.read_text(encoding="utf-8"))
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_tenant_and_project_are_isolated(self):
        store = RailwayBindingStore(self.path)
        store.put(RailwayBinding("tenant-a", "project", "rp", "service", "env", "owner/repo", 1, 1))
        self.assertIsNone(store.get("project", "tenant-b"))


class RailwayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.api = FakeRailwayApi()
        self.service = RailwayIntegrationService(Path(self.temporary.name), api_factory=lambda _token: self.api, clock=lambda: 10)

    def tearDown(self):
        self.temporary.cleanup()

    def test_connect_exposes_no_email_and_token_stays_in_memory(self):
        account = self.service.connect("tenant", TOKEN)
        self.assertEqual(account, {"id": "account-1", "name": "Conta"})
        files = "".join(path.read_text(encoding="utf-8") for path in Path(self.temporary.name).glob("*.json"))
        self.assertNotIn(TOKEN, files)

    def test_link_checks_remote_ownership(self):
        self.service.connect("tenant", TOKEN)
        binding = self.service.link("project", "tenant", "railway-project", "service", "environment", "owner/repo")
        self.assertEqual(binding.repository, "owner/repo")
        with self.assertRaises(PermissionError):
            self.service.link("project", "tenant", "another-project", "service", "environment", "owner/repo")


class RailwayProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        project = self.root / "project"
        project.mkdir()
        (project / "index.html").write_text("<h1>Olympus</h1>", encoding="utf-8")
        self.vault = MemorySecretVault(clock=lambda: 10)
        self.secret = self.vault.put("tenant", "project", "production", "API_KEY", "very-secret-value")
        self.artifact = build_deployment_artifact(project, self.root / "deployment.zip", environment="production", secret_references=(self.secret,))
        self.store = RailwayBindingStore(self.root / "bindings.json")
        self.binding = self.store.put(RailwayBinding("tenant", "project", "railway-project", "service", "environment", "owner/repo", 1, 1))
        self.api = FakeRailwayApi()
        self.provider = RailwayProvider(self.store, lambda _tenant: TOKEN, api_factory=lambda _token: self.api)
        self.coordinator = DeploymentCoordinator(self.vault, (self.provider,))

    def tearDown(self):
        self.temporary.cleanup()

    def request(self, revision=REVISION):
        return DeploymentRequest("tenant", "project", "version", "production", self.artifact, (self.secret,), source_revision=revision)

    def test_deploys_exact_revision_with_scoped_secrets(self):
        result = self.coordinator.deploy("railway", self.request())
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.url, "https://app.up.railway.app")
        self.assertEqual(result.provider_reference, REVISION)
        self.assertEqual(self.api.variables, {"API_KEY": "very-secret-value"})
        self.assertNotIn("very-secret-value", repr(result))

    def test_requires_github_revision(self):
        with self.assertRaisesRegex(DeploymentPolicyError, "GitHub"):
            self.coordinator.deploy("railway", self.request(None))

    def test_blocks_revision_mismatch(self):
        self.api.revision = "b" * 40
        with self.assertRaisesRegex(DeploymentPolicyError, "revisão diferente"):
            self.coordinator.deploy("railway", self.request())

    def test_blocks_provider_that_does_not_attest_revision(self):
        self.api.revision = ""
        with self.assertRaisesRegex(DeploymentPolicyError, "não confirmou"):
            self.coordinator.deploy("railway", self.request())

    def test_domain_and_rollback_stay_in_same_scope(self):
        first = self.coordinator.deploy("railway", self.request())
        self.api.revision = "b" * 40
        second = self.coordinator.deploy("railway", self.request("b" * 40))
        domain = self.coordinator.configure_domain("tenant", "project", "production", "railway", second.deployment_id, "app.example.com")
        self.assertEqual(domain.url, "https://app.example.com")
        self.assertEqual(domain.domain_status, "pending")
        self.assertEqual(domain.dns_records[0].host, "app")
        self.assertEqual(self.coordinator.list("tenant", "project", "production")[-1], domain)
        rolled = self.coordinator.rollback("tenant", "project", "production", "railway", second.deployment_id, first.deployment_id)
        self.assertEqual(rolled.status, "queued")
        self.assertEqual(self.api.rollback_target, first.deployment_id)

    def test_domain_routing_survives_backend_restart(self):
        deployment_store = SQLiteRailwayDeploymentBindingStore(self.root / "railway-deployments.sqlite3")
        record_store = SQLiteDeploymentRecordStore(self.root / "deployment-records.sqlite3")
        first_provider = RailwayProvider(self.store, lambda _tenant: TOKEN, api_factory=lambda _token: self.api, deployment_store=deployment_store)
        first = DeploymentCoordinator(self.vault, (first_provider,), record_store=record_store)
        deployed = first.deploy("railway", self.request())
        restarted_provider = RailwayProvider(
            RailwayBindingStore(self.root / "bindings.json"), lambda _tenant: TOKEN,
            api_factory=lambda _token: self.api,
            deployment_store=SQLiteRailwayDeploymentBindingStore(deployment_store.path),
        )
        restarted = DeploymentCoordinator(self.vault, (restarted_provider,), record_store=SQLiteDeploymentRecordStore(record_store.path))
        configured = restarted.configure_domain("tenant", "project", "production", "railway", deployed.deployment_id, "app.example.com")
        self.assertEqual(configured.domain_status, "pending")
        self.assertEqual(restarted.list("tenant", "project", "production")[-1], configured)


class RailwayBackendContractTests(unittest.TestCase):
    def test_routes_are_tenant_scoped_and_credentials_are_not_returned(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "backend" / "app" / "api" / "railway.py").read_text(encoding="utf-8")
        self.assertIn('identidade_com_permissao("deployments.manage")', source)
        self.assertIn("identity.tenant_id", source)
        self.assertNotIn('return {"token"', source)
        self.assertIn("_GITHUB.sync", source)
        self.assertIn("GitHub e Railway apontam para repositórios diferentes", source)


if __name__ == "__main__":
    unittest.main()
