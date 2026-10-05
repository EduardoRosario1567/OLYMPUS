import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from olympus.distribution import BundlePolicyError, build_public_bundle, verify_public_bundle


class PublicDistributionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.outside_temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "Olympus Runner").write_bytes(b"signed-binary-placeholder")
        (self.root / "Assets").mkdir()
        (self.root / "Assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
        self.target = self.root / "runner.zip"

    def tearDown(self):
        self.temporary.cleanup()
        self.outside_temporary.cleanup()

    def build(self):
        return build_public_bundle(
            self.root,
            self.target,
            version="1.8.0",
            entrypoint="Olympus Runner",
            files=("Olympus Runner", "Assets/logo.svg"),
        )

    def test_public_runner_bundle_is_manifested_and_verifiable(self):
        manifest = self.build()
        verified = verify_public_bundle(self.target)
        self.assertEqual(verified, manifest)
        self.assertEqual(verified.entrypoint, "Olympus Runner")
        with zipfile.ZipFile(self.target) as archive:
            self.assertEqual(set(archive.namelist()), {"Olympus Runner", "Assets/logo.svg", "OLYMPUS-DISTRIBUTION.json"})
            payload = json.loads(archive.read("OLYMPUS-DISTRIBUTION.json"))
            self.assertEqual(payload["bundle_type"], "runner")

    def test_private_source_and_configuration_are_rejected(self):
        for name in ("olympus/pipeline.py", "backend/app/main.py", "frontend/app/page.tsx", "tests/test_core.py", ".env", "app.js", "app.js.map"):
            with self.subTest(name=name):
                with self.assertRaises(BundlePolicyError):
                    build_public_bundle(self.root, self.target, version="1.8", entrypoint=name, files=(name,))

    def test_symlink_and_unlisted_entrypoint_are_rejected(self):
        link = self.root / "Runner Link"
        try:
            link.symlink_to(self.root / "Olympus Runner")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(BundlePolicyError):
            build_public_bundle(self.root, self.target, version="1.8", entrypoint="Runner Link", files=("Runner Link",))
        with self.assertRaises(BundlePolicyError):
            build_public_bundle(self.root, self.target, version="1.8", entrypoint="missing", files=("Olympus Runner",))

    def test_symlinked_parent_cannot_escape_source_root(self):
        outside = Path(self.outside_temporary.name)
        (outside / "binary").write_bytes(b"private")
        link = self.root / "Assets Link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(BundlePolicyError):
            build_public_bundle(self.root, self.target, version="1.8", entrypoint="Assets Link/binary", files=("Assets Link/binary",))

    def test_tampering_is_detected(self):
        self.build()
        modified = self.root / "modified.zip"
        with zipfile.ZipFile(self.target) as source, zipfile.ZipFile(modified, "w") as target:
            for entry in source.infolist():
                payload = source.read(entry.filename)
                target.writestr(entry, b"tampered" if entry.filename == "Olympus Runner" else payload)
        with self.assertRaises(BundlePolicyError):
            verify_public_bundle(modified)

    def test_forged_archive_cannot_smuggle_private_area(self):
        forged = self.root / "forged.zip"
        with zipfile.ZipFile(forged, "w") as archive:
            archive.writestr("Olympus Runner", b"binary")
            archive.writestr("olympus/pipeline.py", b"private")
            archive.writestr("OLYMPUS-DISTRIBUTION.json", "{}")
        with self.assertRaises(BundlePolicyError):
            verify_public_bundle(forged)


if __name__ == "__main__":
    unittest.main()
