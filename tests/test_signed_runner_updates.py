import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from olympus.distribution import (
    RunnerUpdateError,
    RunnerReleaseCatalog,
    build_public_bundle,
    create_signed_release,
    stage_runner_update,
    verify_signed_release,
)


class SignedRunnerUpdateTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("openssl") is None:
            self.skipTest("OpenSSL unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source"
        source.mkdir()
        (source / "Olympus Runner").write_bytes(b"compiled-runner-v1.9")
        (source / "Assets").mkdir()
        (source / "Assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
        self.artifact = self.root / "olympus-runner.zip"
        build_public_bundle(source, self.artifact, version="1.9.0", entrypoint="Olympus Runner",
                            files=("Olympus Runner", "Assets/logo.svg"))
        self.private_key = self.root / "release-private.pem"
        self.public_key = self.root / "release-public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(self.private_key)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        os.chmod(self.private_key, 0o600)
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.private_key), "-pubout", "-out", str(self.public_key)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.manifest = self.root / "release.json"
        self.signature = self.root / "release.sig"

    def tearDown(self):
        if hasattr(self, "temporary"):
            self.temporary.cleanup()

    def create(self, **overrides):
        values = {
            "private_key": self.private_key,
            "public_key": self.public_key,
            "version": "1.9.0",
            "minimum_version": "1.8.0",
            "channel": "stable",
            "platform": "macos",
            "architecture": "x86_64",
            "artifact_url": "https://updates.olympus.example/runner/1.9.0/macos-x86_64.zip",
            "released_at": 1_800_000_000,
        }
        values.update(overrides)
        return create_signed_release(self.artifact, self.manifest, self.signature, **values)

    def verify(self, **overrides):
        values = {
            "public_key": self.public_key,
            "expected_platform": "macos",
            "expected_architecture": "x86_64",
            "expected_channel": "stable",
            "current_version": "1.8.0",
            "now": 1_800_000_100,
        }
        values.update(overrides)
        return verify_signed_release(self.manifest, self.signature, self.artifact, **values)

    def test_signed_release_verifies_and_stages_atomically(self):
        self.create()
        verified = self.verify()
        destination = stage_runner_update(verified, self.root / "staged")
        self.assertEqual(destination.name, "olympus-runner-1.9.0.zip")
        self.assertEqual(destination.read_bytes(), self.artifact.read_bytes())
        self.assertEqual(oct(destination.stat().st_mode & 0o777), "0o600")

    def test_catalog_exposes_only_the_signed_target(self):
        self.create()
        catalog_dir = self.root / "catalog"
        catalog_dir.mkdir()
        basename = "macos-x86_64-stable"
        shutil.copy2(self.manifest, catalog_dir / (basename + ".json"))
        shutil.copy2(self.signature, catalog_dir / (basename + ".sig"))
        shutil.copy2(self.artifact, catalog_dir / (basename + ".zip"))
        verified = RunnerReleaseCatalog(catalog_dir, self.public_key).latest(
            platform="macos", architecture="x86_64", channel="stable",
            current_version="1.8.0", now=1_800_000_100,
        )
        self.assertEqual(verified.release.version, "1.9.0")
        self.assertEqual(verified.canonical_manifest, (catalog_dir / (basename + ".json")).read_bytes())
        with self.assertRaises(RunnerUpdateError):
            RunnerReleaseCatalog(catalog_dir, self.public_key).latest(
                platform="windows", architecture="x86_64", channel="stable",
                current_version="1.8.0", now=1_800_000_100,
            )

    def test_modified_manifest_or_wrong_key_is_rejected(self):
        self.create()
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["artifact_url"] = "https://attacker.example/runner.zip"
        self.manifest.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaises(RunnerUpdateError):
            self.verify()
        other_private = self.root / "other-private.pem"
        other_public = self.root / "other-public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", str(other_private)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["openssl", "pkey", "-in", str(other_private), "-pubout", "-out", str(other_public)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.create()
        with self.assertRaises(RunnerUpdateError):
            self.verify(public_key=other_public)

    def test_tampered_artifact_is_rejected_after_signature(self):
        self.create()
        with self.artifact.open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaisesRegex(RunnerUpdateError, "size|integrity"):
            self.verify()

    def test_target_channel_downgrade_and_old_install_are_blocked(self):
        self.create()
        with self.assertRaisesRegex(RunnerUpdateError, "target"):
            self.verify(expected_architecture="arm64")
        with self.assertRaisesRegex(RunnerUpdateError, "not newer"):
            self.verify(current_version="1.9.0")
        with self.assertRaisesRegex(RunnerUpdateError, "too old"):
            self.verify(current_version="1.7.9")
        with self.assertRaisesRegex(RunnerUpdateError, "cannot exceed"):
            self.create(minimum_version="2.0.0")

    def test_unsafe_url_key_permissions_and_symlink_are_rejected(self):
        with self.assertRaises(RunnerUpdateError):
            self.create(artifact_url="http://updates.example/runner.zip")
        os.chmod(self.private_key, 0o644)
        with self.assertRaisesRegex(RunnerUpdateError, "permissions"):
            self.create()
        os.chmod(self.private_key, 0o600)
        link = self.root / "runner-link.zip"
        try:
            link.symlink_to(self.artifact)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(RunnerUpdateError):
            create_signed_release(link, self.manifest, self.signature, private_key=self.private_key,
                                  public_key=self.public_key, version="1.9.0", minimum_version="1.8.0",
                                  channel="stable", platform="macos", architecture="x86_64",
                                  artifact_url="https://updates.example/runner.zip")

    def test_backend_update_route_requires_runner_auth_and_never_loads_private_key(self):
        source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "api" / "runner.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/releases/latest")', source)
        self.assertIn("_RUNNERS.verify", source)
        self.assertIn("OLYMPUS_RUNNER_RELEASE_PUBLIC_KEY", source)
        self.assertNotIn("RELEASE_PRIVATE_KEY", source)
        self.assertIn("manifest_base64", source)
        self.assertIn("signature_base64", source)


if __name__ == "__main__":
    unittest.main()
