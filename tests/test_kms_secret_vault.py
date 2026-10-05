import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from olympus.cloud.deployment import DeploymentPolicyError, MemorySecretVault
from olympus.cloud.secret_vault import SQLiteKmsSecretVault, configured_secret_vault


class FakeKms:
    """Authenticated test double; production cryptography is owned by managed KMS."""

    def __init__(self, key_id, key):
        self.key_id = key_id
        self.key = key
        self.last_plaintext = None

    @staticmethod
    def context_bytes(context):
        return json.dumps(dict(context), separators=(",", ":"), sort_keys=True).encode()

    def encrypt(self, plaintext, context):
        raw = bytes(plaintext)
        self.last_plaintext = plaintext
        stream = hashlib.sha256(self.key + self.context_bytes(context)).digest()
        encrypted = bytes(value ^ stream[index % len(stream)] for index, value in enumerate(raw))
        tag = hmac.new(self.key, self.context_bytes(context) + encrypted, hashlib.sha256).digest()
        return tag + encrypted

    def decrypt(self, ciphertext, context):
        tag, encrypted = ciphertext[:32], ciphertext[32:]
        expected = hmac.new(self.key, self.context_bytes(context) + encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise DeploymentPolicyError("test KMS authentication failed")
        stream = hashlib.sha256(self.key + self.context_bytes(context)).digest()
        return bytearray(value ^ stream[index % len(stream)] for index, value in enumerate(encrypted))


class FailingReplacement(FakeKms):
    def encrypt(self, plaintext, context):
        if context["name"] == "SECOND_SECRET":
            raise RuntimeError("KMS unavailable")
        return super().encrypt(plaintext, context)


class KmsSecretVaultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name, "secrets.sqlite3")
        self.kms = FakeKms("kms/key/version-1", b"a" * 32)
        self.vault = SQLiteKmsSecretVault(self.path, self.kms, clock=lambda: 1234)

    def tearDown(self):
        self.temporary.cleanup()

    def test_ciphertext_survives_restart_and_plaintext_never_enters_database(self):
        reference = self.vault.put("tenant-a", "project-a", "production", "API_TOKEN", "top-secret-value")
        self.assertNotIn(b"top-secret-value", self.path.read_bytes())
        restarted = SQLiteKmsSecretVault(self.path, self.kms, clock=lambda: 1235)
        with restarted.materialize((reference,)) as values:
            exposed = values["API_TOKEN"]
            self.assertEqual(bytes(exposed), b"top-secret-value")
        self.assertEqual(bytes(exposed), b"\x00" * len(b"top-secret-value"))
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")

    def test_associated_context_prevents_ciphertext_relocation(self):
        reference = self.vault.put("tenant-a", "project-a", "production", "API_TOKEN", "secret")
        with self.vault._connect() as connection:
            connection.execute(
                "UPDATE deployment_secrets SET project_id='project-b' WHERE tenant_id='tenant-a' AND project_id='project-a'"
            )
        moved = type(reference)("tenant-a", "project-b", "production", "API_TOKEN", reference.version, reference.updated_at)
        with self.assertRaises(DeploymentPolicyError):
            with self.vault.materialize((moved,)):
                pass

    def test_rotation_invalidates_stale_reference(self):
        first = self.vault.put("tenant-a", "project-a", "preview", "API_TOKEN", "first")
        second = self.vault.put("tenant-a", "project-a", "preview", "API_TOKEN", "second")
        with self.assertRaises(DeploymentPolicyError):
            with self.vault.materialize((first,)):
                pass
        with self.vault.materialize((second,)) as values:
            self.assertEqual(bytes(values["API_TOKEN"]), b"second")

    def test_kms_rewrap_is_atomic_and_preserves_versions(self):
        first = self.vault.put("tenant-a", "project-a", "production", "FIRST_SECRET", "one")
        second = self.vault.put("tenant-a", "project-a", "production", "SECOND_SECRET", "two")
        failing = FailingReplacement("kms/key/version-2", b"b" * 32)
        with self.assertRaises(RuntimeError):
            self.vault.rewrap(failing)
        with self.vault.materialize((first, second)) as values:
            self.assertEqual(bytes(values["FIRST_SECRET"]), b"one")
            self.assertEqual(bytes(values["SECOND_SECRET"]), b"two")
        replacement = FakeKms("kms/key/version-2", b"b" * 32)
        self.assertEqual(self.vault.rewrap(replacement), 2)
        restarted = SQLiteKmsSecretVault(self.path, replacement)
        self.assertEqual(restarted.list("tenant-a", "project-a", "production"), (first, second))
        with restarted.materialize((first, second)) as values:
            self.assertEqual(bytes(values["FIRST_SECRET"]), b"one")
            self.assertEqual(bytes(values["SECOND_SECRET"]), b"two")

    def test_wrong_key_and_scope_fail_closed(self):
        reference = self.vault.put("tenant-a", "project-a", "production", "API_TOKEN", "secret")
        wrong = SQLiteKmsSecretVault(self.path, FakeKms("kms/key/version-2", b"z" * 32))
        with self.assertRaises(DeploymentPolicyError):
            with wrong.materialize((reference,)):
                pass
        self.assertEqual(wrong.list("tenant-b", "project-a", "production"), ())

    def test_runtime_composition_defaults_to_memory_and_loads_explicit_kms(self):
        self.assertIsInstance(configured_secret_vault(self.path.parent), MemorySecretVault)
        module = SimpleNamespace(build=lambda: self.kms)
        with patch("olympus.cloud.secret_vault.importlib.import_module", return_value=module):
            configured = configured_secret_vault(self.path.parent / "configured", "vendor.adapter:build")
        self.assertIsInstance(configured, SQLiteKmsSecretVault)
        with self.assertRaises(RuntimeError):
            configured_secret_vault(self.path.parent, "unsafe-spec")


if __name__ == "__main__":
    unittest.main()
