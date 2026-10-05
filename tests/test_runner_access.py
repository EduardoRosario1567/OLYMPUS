import tempfile
import unittest
from pathlib import Path

from olympus.distribution import AccessDenied, RunnerRegistry, SQLiteRunnerStateStore


class MutableClock:
    def __init__(self, value=1_800_000_000):
        self.value = value

    def __call__(self):
        return self.value


class RunnerAccessTests(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.registry = RunnerRegistry(b"k" * 32, clock=self.clock, access_ttl_seconds=120)

    def activate(self, tenant="tenant-a", installation="device-001", license_id="license-pro"):
        ticket = self.registry.create_enrollment(tenant, license_id)
        return ticket, self.registry.activate(ticket.code, installation, platform="macos", runner_version="1.8.0")

    def test_one_time_enrollment_issues_short_credential(self):
        ticket, credential = self.activate()
        claims = self.registry.verify(credential.access_token, tenant_id="tenant-a")
        self.assertEqual(claims.installation_id, "device-001")
        self.assertEqual(credential.access_expires_at, self.clock.value + 120)
        with self.assertRaises(AccessDenied):
            self.registry.activate(ticket.code, "device-002", platform="macos", runner_version="1.8.0")

    def test_refresh_rotates_and_invalidates_previous_secret(self):
        _, first = self.activate()
        second = self.registry.rotate(first.refresh_token)
        self.assertNotEqual(first.refresh_token, second.refresh_token)
        with self.assertRaises(AccessDenied):
            self.registry.rotate(first.refresh_token)
        self.assertEqual(self.registry.verify(second.access_token).installation_id, "device-001")

    def test_expired_access_and_license_are_rejected(self):
        _, credential = self.activate()
        self.clock.value += 121
        with self.assertRaises(AccessDenied):
            self.registry.verify(credential.access_token)
        with self.assertRaises(AccessDenied):
            self.registry.create_enrollment("tenant-a", "license-pro", license_expires_at=self.clock.value)

    def test_revocation_invalidates_access_and_refresh_immediately(self):
        _, credential = self.activate()
        revoked = self.registry.revoke("tenant-a", "device-001")
        self.assertIsNotNone(revoked.revoked_at)
        with self.assertRaises(AccessDenied):
            self.registry.verify(credential.access_token)
        with self.assertRaises(AccessDenied):
            self.registry.rotate(credential.refresh_token)

    def test_tenant_cannot_verify_list_or_revoke_another_runner(self):
        _, credential = self.activate()
        with self.assertRaises(AccessDenied):
            self.registry.verify(credential.access_token, tenant_id="tenant-b")
        self.assertEqual(self.registry.list_installations("tenant-b"), [])
        with self.assertRaises(AccessDenied):
            self.registry.revoke("tenant-b", "device-001")

    def test_tampered_token_and_weak_server_key_are_rejected(self):
        _, credential = self.activate()
        tampered = credential.access_token[:-1] + ("A" if credential.access_token[-1] != "A" else "B")
        with self.assertRaises(AccessDenied):
            self.registry.verify(tampered)
        with self.assertRaises(ValueError):
            RunnerRegistry(b"weak")

    def test_secrets_are_not_exposed_by_object_representation(self):
        ticket, credential = self.activate()
        self.assertNotIn(ticket.code, repr(ticket))
        self.assertNotIn(credential.refresh_token, repr(credential))
        self.assertNotIn(credential.access_token, repr(credential))

    def test_duplicate_active_installation_is_rejected(self):
        self.activate()
        ticket = self.registry.create_enrollment("tenant-a", "license-pro")
        with self.assertRaises(AccessDenied):
            self.registry.activate(ticket.code, "device-001", platform="macos", runner_version="1.8.1")

    def test_same_local_installation_id_isolated_between_tenants(self):
        _, first = self.activate(tenant="tenant-a", installation="device-001")
        _, second = self.activate(tenant="tenant-b", installation="device-001", license_id="license-team")
        self.assertEqual(self.registry.verify(first.access_token).tenant_id, "tenant-a")
        self.assertEqual(self.registry.verify(second.access_token).tenant_id, "tenant-b")
        self.registry.revoke("tenant-a", "device-001")
        self.assertEqual(self.registry.verify(second.access_token).tenant_id, "tenant-b")

    def test_noncanonical_or_unicode_token_is_rejected_safely(self):
        _, credential = self.activate()
        with self.assertRaises(AccessDenied):
            self.registry.verify(credential.access_token + "=")
        with self.assertRaises(AccessDenied):
            self.registry.verify("olr1.á.invalid")

    def test_invalid_identifiers_platforms_and_long_ttl_are_rejected(self):
        for tenant in ("", "../tenant", "a b"):
            with self.subTest(tenant=tenant), self.assertRaises(ValueError):
                self.registry.create_enrollment(tenant, "license-pro")
        ticket = self.registry.create_enrollment("tenant-a", "license-pro")
        with self.assertRaises(ValueError):
            self.registry.activate(ticket.code, "device-001", platform="ios", runner_version="1.8.0")
        with self.assertRaises(ValueError):
            self.registry.create_enrollment("tenant-a", "license-pro", ttl_seconds=601)

    def test_sqlite_state_survives_restart_without_storing_raw_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "runner.sqlite3")
            first = RunnerRegistry(b"k" * 32, clock=self.clock, access_ttl_seconds=120, state_store=SQLiteRunnerStateStore(path))
            ticket = first.create_enrollment("tenant-a", "license-pro")
            credential = first.activate(ticket.code, "device-001", platform="macos", runner_version="1.9.0")
            second = RunnerRegistry(b"k" * 32, clock=self.clock, access_ttl_seconds=120, state_store=SQLiteRunnerStateStore(path))
            rotated = second.rotate(credential.refresh_token)
            self.assertEqual(second.verify(rotated.access_token).installation_id, "device-001")
            stored = path.read_bytes()
            self.assertNotIn(ticket.code.encode(), stored)
            self.assertNotIn(credential.refresh_token.encode(), stored)
            self.assertNotIn(credential.access_token.encode(), stored)
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_revocation_survives_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "runner.sqlite3")
            first = RunnerRegistry(b"k" * 32, clock=self.clock, state_store=SQLiteRunnerStateStore(path))
            ticket = first.create_enrollment("tenant-a", "license-pro")
            credential = first.activate(ticket.code, "device-001", platform="macos", runner_version="1.9.0")
            first.revoke("tenant-a", "device-001")
            second = RunnerRegistry(b"k" * 32, clock=self.clock, state_store=SQLiteRunnerStateStore(path))
            with self.assertRaises(AccessDenied):
                second.verify(credential.access_token)

    def test_corrupted_persistent_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = SQLiteRunnerStateStore(Path(temporary, "runner.sqlite3"))
            store.save({"pending": "invalid"})
            with self.assertRaises(RuntimeError):
                RunnerRegistry(b"k" * 32, state_store=store)

    def test_persistent_state_rejects_signing_key_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = SQLiteRunnerStateStore(Path(temporary, "runner.sqlite3"))
            first = RunnerRegistry(b"k" * 32, state_store=store)
            first.create_enrollment("tenant-a", "license-pro")
            with self.assertRaises(RuntimeError):
                RunnerRegistry(b"z" * 32, state_store=store)


if __name__ == "__main__":
    unittest.main()
