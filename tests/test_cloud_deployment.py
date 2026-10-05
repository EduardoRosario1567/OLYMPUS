from pathlib import Path
import json
import tempfile
import unittest
import zipfile

from olympus.cloud.deployment import (
    DEPLOYMENT_MANIFEST,
    DeploymentCoordinator,
    DeploymentPolicyError,
    DeploymentRequest,
    MemorySecretVault,
    ProviderDeployment,
    SQLiteDeploymentRecordStore,
    build_deployment_artifact,
    verify_deployment_artifact,
)


class FakeProvider:
    provider_id = "provider-test"

    def __init__(self):
        self.calls = []
        self.retained_secret = None

    def deploy(self, request, secrets):
        self.retained_secret = next(iter(secrets.values()), None)
        self.calls.append(("deploy", request.project_id, tuple(sorted(secrets))))
        deployment_count = sum(1 for call in self.calls if call[0] == "deploy")
        return ProviderDeployment(self.provider_id, "deploy-%03d" % deployment_count, "ready", "https://example.test/app")

    def rollback(self, deployment_id, target_deployment_id):
        self.calls.append(("rollback", deployment_id, target_deployment_id))
        return ProviderDeployment(self.provider_id, "deploy-rollback", "ready", "https://example.test/app")

    def configure_domain(self, deployment_id, domain):
        self.calls.append(("domain", deployment_id, domain))
        return ProviderDeployment(self.provider_id, deployment_id, "ready", "https://" + domain)


class CloudDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.target = Path(self.temporary.name) / "deployment.zip"
        self.vault = MemorySecretVault(clock=lambda: 1234)
        self.provider = FakeProvider()
        self.coordinator = DeploymentCoordinator(self.vault, (self.provider,))

    def tearDown(self):
        self.temporary.cleanup()

    def test_static_artifact_contains_names_but_never_secret_values(self):
        (self.root / "index.html").write_text("<h1>Olympus</h1>", encoding="utf-8")
        (self.root / ".env").write_text("API_KEY=never-export-this", encoding="utf-8")
        (self.root / "attachments").mkdir()
        (self.root / "attachments" / "private.pdf").write_bytes(b"private")
        ref = self.vault.put("tenant-a", "project-a", "production", "API_KEY", "never-export-this")
        artifact = build_deployment_artifact(self.root, self.target, environment="production", secret_references=(ref,))
        self.assertEqual(artifact.runtime, "static")
        self.assertEqual(artifact.secret_names, ("API_KEY",))
        self.assertNotIn("never-export-this", self.target.read_bytes().decode("latin-1"))
        with zipfile.ZipFile(self.target) as archive:
            self.assertEqual(set(archive.namelist()), {"index.html", DEPLOYMENT_MANIFEST})
            manifest = json.loads(archive.read(DEPLOYMENT_MANIFEST))
            self.assertEqual(manifest["secret_names"], ["API_KEY"])

    def test_runtime_detection_supports_node_python_and_container(self):
        cases = (
            ("node", {"package.json": "{}"}),
            ("python", {"requirements.txt": "fastapi", "main.py": "app = 1"}),
            ("container", {"Dockerfile": "FROM scratch", "index.html": "ok"}),
        )
        for runtime, files in cases:
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name, content in files.items():
                    (root / name).write_text(content, encoding="utf-8")
                artifact = build_deployment_artifact(root, root.parent / (root.name + ".zip"), environment="preview")
                self.assertEqual(artifact.runtime, runtime)

    def test_unsupported_project_and_cross_environment_secret_are_rejected(self):
        (self.root / "notes.txt").write_text("not runnable", encoding="utf-8")
        with self.assertRaises(DeploymentPolicyError):
            build_deployment_artifact(self.root, self.target, environment="production")
        (self.root / "index.html").write_text("ok", encoding="utf-8")
        ref = self.vault.put("tenant-a", "project-a", "preview", "TOKEN", "secret")
        with self.assertRaises(DeploymentPolicyError):
            build_deployment_artifact(self.root, self.target, environment="production", secret_references=(ref,))

    def test_vault_is_tenant_project_and_environment_scoped(self):
        a = self.vault.put("tenant-a", "project-a", "preview", "TOKEN", "alpha")
        b = self.vault.put("tenant-b", "project-a", "preview", "TOKEN", "beta")
        c = self.vault.put("tenant-a", "project-a", "production", "TOKEN", "prod")
        self.assertEqual(self.vault.list("tenant-a", "project-a", "preview"), (a,))
        self.assertEqual(self.vault.list("tenant-b", "project-a", "preview"), (b,))
        self.assertEqual(self.vault.list("tenant-a", "project-a", "production"), (c,))

    def test_secret_rotation_invalidates_stale_reference_and_material_is_wiped(self):
        stale = self.vault.put("tenant-a", "project-a", "preview", "TOKEN", "first")
        current = self.vault.put("tenant-a", "project-a", "preview", "TOKEN", "second")
        with self.assertRaises(DeploymentPolicyError):
            with self.vault.materialize((stale,)):
                pass
        exposed = None
        with self.vault.materialize((current,)) as secrets:
            exposed = secrets["TOKEN"]
            self.assertEqual(bytes(exposed), b"second")
        self.assertEqual(bytes(exposed), b"\x00" * len(b"second"))

    def test_vault_never_returns_values_in_reference_or_listing(self):
        ref = self.vault.put("tenant-a", "project-a", "preview", "TOKEN", "top-secret")
        self.assertNotIn("top-secret", repr(ref))
        self.assertNotIn("top-secret", repr(self.vault.list("tenant-a", "project-a", "preview")))
        self.assertTrue(self.vault.delete("tenant-a", "project-a", "preview", "TOKEN"))
        self.assertFalse(self.vault.delete("tenant-a", "project-a", "preview", "TOKEN"))

    def test_invalid_secret_and_environment_are_rejected(self):
        for name in ("token", "A", "../TOKEN", "TOKEN-NAME"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.vault.put("tenant-a", "project-a", "preview", name, "value")
        with self.assertRaises(ValueError):
            self.vault.put("tenant-a", "project-a", "staging", "TOKEN", "value")
        with self.assertRaises(ValueError):
            self.vault.put("tenant-a", "project-a", "preview", "TOKEN", "")

    def test_symlink_and_tampered_artifact_are_rejected(self):
        (self.root / "index.html").write_text("safe", encoding="utf-8")
        link = self.root / "outside"
        try:
            link.symlink_to(Path(self.temporary.name) / "missing")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(DeploymentPolicyError):
            build_deployment_artifact(self.root, self.target, environment="preview")
        link.unlink()
        build_deployment_artifact(self.root, self.target, environment="preview")
        forged = Path(self.temporary.name) / "forged.zip"
        with zipfile.ZipFile(self.target) as source, zipfile.ZipFile(forged, "w") as target:
            for item in source.infolist():
                data = source.read(item.filename)
                target.writestr(item, b"changed" if item.filename == "index.html" else data)
        with self.assertRaises(DeploymentPolicyError):
            verify_deployment_artifact(forged)

    def deployment_request(self, reference=None, tenant="tenant-a", project="project-a", domain=None):
        (self.root / "index.html").write_text("safe", encoding="utf-8")
        references = (reference,) if reference is not None else ()
        artifact = build_deployment_artifact(self.root, self.target, environment="production", secret_references=references)
        return DeploymentRequest(tenant, project, "version-001", "production", artifact, references, domain)

    def test_coordinator_materializes_secret_only_during_provider_call(self):
        ref = self.vault.put("tenant-a", "project-a", "production", "TOKEN", "top-secret")
        result = self.coordinator.deploy("provider-test", self.deployment_request(ref))
        self.assertEqual(result.status, "ready")
        self.assertEqual(self.provider.calls, [("deploy", "project-a", ("TOKEN",))])
        self.assertEqual(bytes(self.provider.retained_secret), b"\x00" * len(b"top-secret"))
        self.assertNotIn("top-secret", repr(result))

    def test_coordinator_rejects_cross_scope_or_missing_secret_before_provider(self):
        foreign = self.vault.put("tenant-b", "project-a", "production", "TOKEN", "foreign")
        with self.assertRaises(DeploymentPolicyError):
            self.coordinator.deploy("provider-test", self.deployment_request(foreign))
        self.assertEqual(self.provider.calls, [])

        local = self.vault.put("tenant-a", "project-a", "production", "TOKEN", "local")
        request = self.deployment_request(local)
        missing = DeploymentRequest(request.tenant_id, request.project_id, request.version_id, request.environment, request.artifact, ())
        with self.assertRaises(DeploymentPolicyError):
            self.coordinator.deploy("provider-test", missing)
        self.assertEqual(self.provider.calls, [])

    def test_artifact_tampering_is_rejected_before_provider(self):
        request = self.deployment_request()
        with self.target.open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaises(DeploymentPolicyError):
            self.coordinator.deploy("provider-test", request)
        self.assertEqual(self.provider.calls, [])

    def test_artifact_metadata_forgery_is_rejected_before_provider(self):
        request = self.deployment_request()
        forged_artifact = type(request.artifact)(
            request.artifact.artifact_id,
            request.artifact.path,
            request.artifact.sha256,
            request.artifact.runtime,
            request.artifact.entrypoint,
            request.artifact.environment,
            request.artifact.file_count + 1,
            request.artifact.size_bytes,
            request.artifact.secret_names,
        )
        forged = DeploymentRequest(request.tenant_id, request.project_id, request.version_id, request.environment, forged_artifact)
        with self.assertRaises(DeploymentPolicyError):
            self.coordinator.deploy("provider-test", forged)
        self.assertEqual(self.provider.calls, [])

    def test_domain_and_rollback_are_tenant_scoped(self):
        request = self.deployment_request(domain="app.exemplo.com.br")
        deployed = self.coordinator.deploy("provider-test", request)
        configured = self.coordinator.configure_domain("tenant-a", "project-a", "production", "provider-test", deployed.deployment_id, "App.Exemplo.com.br.")
        self.assertEqual(configured.url, "https://app.exemplo.com.br")
        second = self.coordinator.deploy("provider-test", self.deployment_request())
        rolled_back = self.coordinator.rollback("tenant-a", "project-a", "production", "provider-test", second.deployment_id, deployed.deployment_id)
        self.assertEqual(rolled_back.deployment_id, "deploy-rollback")
        with self.assertRaises(DeploymentPolicyError):
            self.coordinator.rollback("tenant-b", "project-a", "production", "provider-test", second.deployment_id, deployed.deployment_id)

    def test_invalid_domain_and_unsafe_provider_response_are_rejected(self):
        request = self.deployment_request()
        deployed = self.coordinator.deploy("provider-test", request)
        for domain in ("http://example.com", "localhost", "example.com/path", "-bad.example"):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                self.coordinator.configure_domain("tenant-a", "project-a", "production", "provider-test", deployed.deployment_id, domain)

        class UnsafeProvider(FakeProvider):
            provider_id = "unsafe-provider"

            def deploy(self, request, secrets):
                return ProviderDeployment(self.provider_id, "unsafe-001", "ready", "http://insecure.test")

        coordinator = DeploymentCoordinator(self.vault, (UnsafeProvider(),))
        with self.assertRaises(DeploymentPolicyError):
            coordinator.deploy("unsafe-provider", request)

    def test_deployment_history_and_ownership_survive_restart(self):
        store = SQLiteDeploymentRecordStore(Path(self.temporary.name, "deployments.sqlite3"))
        first = DeploymentCoordinator(self.vault, (self.provider,), record_store=store)
        deployed = first.deploy("provider-test", self.deployment_request())
        restarted_provider = FakeProvider()
        restarted = DeploymentCoordinator(self.vault, (restarted_provider,), record_store=SQLiteDeploymentRecordStore(store.path))
        self.assertEqual(restarted.list("tenant-a", "project-a", "production"), (deployed,))
        configured = restarted.configure_domain("tenant-a", "project-a", "production", "provider-test", deployed.deployment_id, "app.example.com")
        self.assertEqual(restarted.list("tenant-a", "project-a", "production")[-1], configured)
        with self.assertRaises(DeploymentPolicyError):
            restarted.configure_domain("tenant-b", "project-a", "production", "provider-test", deployed.deployment_id, "app.example.com")
        self.assertEqual(oct(store.path.stat().st_mode & 0o777), "0o600")


if __name__ == "__main__":
    unittest.main()
