import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.cloud.project_versions import ProjectVersionStore
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class ProjectVersionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.projects = ProjectWorkspaceManager(Path(self.temporary.name, "cloud"))
        self.project = self.projects.create("Projeto", "project-1", tenant_id="tenant-a")
        self.versions = ProjectVersionStore(self.projects, Path(self.temporary.name, "versions"))
        self.root = Path(self.project.root)

    def test_capture_list_and_compare_with_current_project(self):
        Path(self.root, "index.html").write_text("v1", encoding="utf-8")
        first = self.versions.capture("project-1", "Primeira versão", tenant_id="tenant-a")
        Path(self.root, "index.html").write_text("v2", encoding="utf-8")
        Path(self.root, "novo.css").write_text("body{}", encoding="utf-8")
        comparison = self.versions.compare("project-1", first.version_id, tenant_id="tenant-a")
        self.assertEqual(comparison["modified"], ["index.html"])
        self.assertEqual(comparison["deleted"], ["novo.css"])
        self.assertEqual(self.versions.list("project-1", "tenant-a")[0].label, "Primeira versão")

    def test_restore_creates_safety_backup_and_preserves_secrets_and_attachments(self):
        Path(self.root, "src").mkdir()
        Path(self.root, "src", "app.js").write_text("old", encoding="utf-8")
        Path(self.root, "src", ".env.local").write_text("SECRET=one", encoding="utf-8")
        Path(self.root, "attachments").mkdir()
        Path(self.root, "attachments", "brief.txt").write_text("keep", encoding="utf-8")
        first = self.versions.capture("project-1", "Estável", tenant_id="tenant-a")

        Path(self.root, "src", "app.js").write_text("new", encoding="utf-8")
        Path(self.root, "src", ".env.local").write_text("SECRET=two", encoding="utf-8")
        Path(self.root, "extra.txt").write_text("remove", encoding="utf-8")
        restored, safety = self.versions.restore("project-1", first.version_id, tenant_id="tenant-a")

        self.assertEqual(restored.version_id, first.version_id)
        self.assertEqual(safety.reason, "pre_restore")
        self.assertEqual(Path(self.root, "src", "app.js").read_text(encoding="utf-8"), "old")
        self.assertEqual(Path(self.root, "src", ".env.local").read_text(encoding="utf-8"), "SECRET=two")
        self.assertEqual(Path(self.root, "attachments", "brief.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse(Path(self.root, "extra.txt").exists())

    def test_corrupt_version_is_rejected_before_project_mutation(self):
        Path(self.root, "index.html").write_text("stable", encoding="utf-8")
        version = self.versions.capture("project-1", tenant_id="tenant-a")
        bucket = self.versions._bucket("project-1", "tenant-a")
        Path(bucket, version.version_id, "files", "index.html").write_text("corrupt", encoding="utf-8")
        Path(self.root, "index.html").write_text("current", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.versions.restore("project-1", version.version_id, tenant_id="tenant-a")
        self.assertEqual(Path(self.root, "index.html").read_text(encoding="utf-8"), "current")

    def test_failed_post_restore_verification_rolls_back_current_project(self):
        Path(self.root, "index.html").write_text("old", encoding="utf-8")
        version = self.versions.capture("project-1", tenant_id="tenant-a")
        Path(self.root, "index.html").write_text("current", encoding="utf-8")
        Path(self.root, "current.css").write_text("keep", encoding="utf-8")
        real_inventory = self.versions._inventory
        with patch.object(self.versions, "_inventory", side_effect=lambda root: real_inventory(root) if root.name == "files" else {}):
            with self.assertRaisesRegex(ValueError, "verification"):
                self.versions.restore("project-1", version.version_id, tenant_id="tenant-a")
        self.assertEqual(Path(self.root, "index.html").read_text(encoding="utf-8"), "current")
        self.assertTrue(Path(self.root, "current.css").is_file())

    def test_symbolic_links_are_rejected_instead_of_silently_lost(self):
        Path(self.root, "index.html").write_text("ok", encoding="utf-8")
        try:
            Path(self.root, "linked.html").symlink_to("index.html")
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links unavailable")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            self.versions.capture("project-1", tenant_id="tenant-a")

    def test_snapshot_size_limit_is_checked_before_copy(self):
        Path(self.root, "large.txt").write_text("large", encoding="utf-8")
        with patch("olympus.cloud.project_versions.MAX_VERSION_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "too large"):
                self.versions.capture("project-1", tenant_id="tenant-a")
        self.assertEqual(self.versions.list("project-1", "tenant-a"), [])

    def test_runtime_dependencies_and_build_cache_are_not_versioned(self):
        Path(self.root, "index.html").write_text("source", encoding="utf-8")
        Path(self.root, "node_modules", "pkg").mkdir(parents=True)
        Path(self.root, "node_modules", "pkg", "large.js").write_text("dependency", encoding="utf-8")
        Path(self.root, ".next").mkdir()
        Path(self.root, ".next", "cache.js").write_text("cache", encoding="utf-8")
        version = self.versions.capture("project-1", tenant_id="tenant-a")
        bucket = self.versions._bucket("project-1", "tenant-a")
        files = Path(bucket, version.version_id, "files")
        self.assertTrue(Path(files, "index.html").is_file())
        self.assertFalse(Path(files, "node_modules").exists())
        self.assertFalse(Path(files, ".next").exists())

    def test_protected_file_in_snapshot_is_rejected_before_mutation(self):
        Path(self.root, "index.html").write_text("old", encoding="utf-8")
        version = self.versions.capture("project-1", tenant_id="tenant-a")
        bucket = self.versions._bucket("project-1", "tenant-a")
        Path(bucket, version.version_id, "files", ".env").write_text("INJECTED=yes", encoding="utf-8")
        Path(self.root, "index.html").write_text("current", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.versions.restore("project-1", version.version_id, tenant_id="tenant-a")
        self.assertEqual(Path(self.root, "index.html").read_text(encoding="utf-8"), "current")
        self.assertFalse(Path(self.root, ".env").exists())

    def test_publish_execution_versions_before_and_after_promotion(self):
        Path(self.root, "index.html").write_text("before", encoding="utf-8")
        workspace = self.projects.execution_workspace("project-1", "exec-1", tenant_id="tenant-a")
        Path(workspace, "index.html").write_text("after", encoding="utf-8")
        promoted, before, after = self.versions.publish_execution(
            "project-1", "exec-1", ["index.html"], tenant_id="tenant-a"
        )
        self.assertEqual(promoted, ("index.html",))
        self.assertEqual(before.reason, "pre_publish")
        self.assertEqual(after.reason, "mission")
        self.assertEqual(Path(self.root, "index.html").read_text(encoding="utf-8"), "after")
        comparison = self.versions.compare("project-1", before.version_id, after.version_id, "tenant-a")
        self.assertEqual(comparison["modified"], ["index.html"])

    def test_tenant_cannot_access_versions(self):
        version = self.versions.capture("project-1", tenant_id="tenant-a")
        with self.assertRaises(KeyError):
            self.versions.list("project-1", tenant_id="tenant-b")
        with self.assertRaises(KeyError):
            self.versions.restore("project-1", version.version_id, tenant_id="tenant-b")


if __name__ == "__main__":
    unittest.main()
