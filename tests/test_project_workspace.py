import tempfile
import unittest
from pathlib import Path

from olympus.cloud.project_workspace import ProjectWorkspaceManager


class TestProjectWorkspaceManager(unittest.TestCase):
    def test_create_get_list_and_stable_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            project = mgr.create("HUB Trust", "hub-trust")
            self.assertEqual(project.project_id, "hub-trust")
            self.assertEqual(mgr.get("hub-trust").name, "HUB Trust")
            self.assertEqual(len(mgr.list()), 1)
            self.assertTrue(Path(project.root).is_dir())

    def test_execution_workspaces_are_isolated_under_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            project = mgr.create("Olympus")
            a = mgr.execution_workspace(project.project_id, "exec-a")
            b = mgr.execution_workspace(project.project_id, "exec-b")
            self.assertNotEqual(a, b)
            self.assertEqual(a.parent, b.parent)
            self.assertTrue(a.parent.name == ".executions")

    def test_projects_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            a = mgr.create("A", "a")
            b = mgr.create("B", "b")
            self.assertNotEqual(mgr.project_root("a"), mgr.project_root("b"))

    def test_duplicate_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            mgr.create("A", "a")
            with self.assertRaises(ValueError):
                mgr.create("A2", "a")

    def test_execution_snapshot_is_promoted_and_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            project = mgr.create("Google Demo", "google-demo")
            Path(project.root, "README.md").write_text("seed", encoding="utf-8")
            Path(project.root, ".env").write_text("SECRET=hidden", encoding="utf-8")
            Path(project.root, "src").mkdir()
            Path(project.root, "src", ".env.local").write_text("SECRET=nested", encoding="utf-8")
            Path(project.root, "node_modules", "pkg").mkdir(parents=True)
            Path(project.root, "node_modules", "pkg", "index.js").write_text("dependency", encoding="utf-8")
            Path(project.root, ".next").mkdir()
            Path(project.root, ".next", "cache").write_text("generated", encoding="utf-8")

            workspace = mgr.execution_workspace("google-demo", "exec-1")
            self.assertEqual(Path(workspace, "README.md").read_text(encoding="utf-8"), "seed")
            self.assertFalse(Path(workspace, "node_modules").exists())
            self.assertFalse(Path(workspace, ".next").exists())
            self.assertFalse(Path(workspace, ".env").exists())
            self.assertFalse(Path(workspace, "src", ".env.local").exists())
            Path(workspace, "app").mkdir()
            Path(workspace, "app", "index.html").write_text("<h1>Google Demo</h1>", encoding="utf-8")

            promoted = mgr.promote_execution_files(
                "google-demo", "exec-1", ["app/index.html"]
            )
            self.assertEqual(promoted, ("app/index.html",))
            self.assertTrue(Path(project.root, "app", "index.html").is_file())

            archive = mgr.export_zip("google-demo")
            self.assertTrue(archive.is_file())
            import zipfile
            with zipfile.ZipFile(archive) as zipped:
                self.assertIn("app/index.html", zipped.namelist())
                self.assertNotIn(".executions/exec-1/app/index.html", zipped.namelist())
                self.assertNotIn(".env", zipped.namelist())
                self.assertFalse(any(name.startswith("node_modules/") for name in zipped.namelist()))
                self.assertFalse(any(name.startswith(".next/") for name in zipped.namelist()))


if __name__ == "__main__":
    unittest.main()
