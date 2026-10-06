import io
import json
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.cloud.project_studio import PREVIEW_ISOLATION_MESSAGE, ProjectFileEditor, ProjectRuntimeManager, RuntimeSession
from olympus.cloud.preview_container import PreviewLifecycleError
from olympus.cloud.project_versions import ProjectVersionStore
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class ProjectFileEditorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.projects = ProjectWorkspaceManager(self.temporary.name)
        self.project = self.projects.create("Studio", "studio", tenant_id="tenant-a")
        self.root = Path(self.project.root)
        self.versions = ProjectVersionStore(self.projects, Path(self.temporary.name) / "versions")
        self.editor = ProjectFileEditor(self.projects, self.versions)

    def test_lists_and_reads_only_safe_utf8_source_files(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "page.tsx").write_text("export default 1", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=x", encoding="utf-8")
        (self.root / "binary.png").write_bytes(b"\x89PNG")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "leak.js").write_text("x", encoding="utf-8")
        records = self.editor.list("studio", "tenant-a")
        self.assertEqual([item.path for item in records], ["src/page.tsx"])
        record, content = self.editor.read("studio", "src/page.tsx", "tenant-a")
        self.assertEqual(content, "export default 1")
        self.assertEqual(len(record.sha256), 64)

    def test_save_creates_backup_and_uses_optimistic_lock(self):
        target = self.root / "index.html"
        target.write_text("antes", encoding="utf-8")
        record, _ = self.editor.read("studio", "index.html", "tenant-a")
        saved, backup = self.editor.save("studio", "index.html", "depois", record.sha256, "tenant-a")
        self.assertEqual(target.read_text(encoding="utf-8"), "depois")
        self.assertEqual(backup.reason, "pre_edit")
        self.assertNotEqual(saved.sha256, record.sha256)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.editor.save("studio", "index.html", "conflito", record.sha256, "tenant-a")

    def test_blocks_traversal_secrets_symlinks_and_cross_tenant_access(self):
        (self.root / "index.html").write_text("ok", encoding="utf-8")
        for unsafe in ("../index.html", ".env", "attachments/file.txt", "node_modules/x.js"):
            with self.assertRaises((ValueError, KeyError)):
                self.editor.read("studio", unsafe, "tenant-a")
        with self.assertRaises(KeyError):
            self.editor.list("studio", "tenant-b")
        link = self.root / "linked.js"
        try:
            link.symlink_to(self.root / "index.html")
        except OSError:
            self.skipTest("symbolic links unavailable")
        with self.assertRaises(ValueError):
            self.editor.read("studio", "linked.js", "tenant-a")


class FakeProcess:
    def __init__(self):
        self.stdout = io.StringIO("")
        self.returncode = None
        self.pid = 12345

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class ProjectRuntimeManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.projects = ProjectWorkspaceManager(self.temporary.name)
        self.project = self.projects.create("Web", "web", tenant_id="tenant-a")
        self.root = Path(self.project.root)
        self.manager = ProjectRuntimeManager(self.projects, ttl_seconds=60)

    def make_package(self, script="next dev", dependency="next"):
        (self.root / "package.json").write_text(json.dumps({"scripts": {"dev": script}, "dependencies": {dependency: "1"}}), encoding="utf-8")

    def test_detects_supported_runtime_without_installing_dependencies(self):
        self.make_package()
        info = self.manager.detect("web", "tenant-a")
        self.assertEqual(info["framework"], "Next.js")
        self.assertFalse(info["ready"])
        self.assertIn("Dependências", info["message"])

    def test_rejects_arbitrary_package_scripts(self):
        self.make_package("next dev && curl example.com")
        info = self.manager.detect("web", "tenant-a")
        self.assertEqual(info["kind"], "unsupported")

    def test_rejects_node_modules_symlinked_outside_project(self):
        self.make_package()
        outside = Path(self.temporary.name) / "outside-modules"
        binary = outside / "next" / "dist" / "bin" / "next"
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
        try:
            (self.root / "node_modules").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symbolic links unavailable")
        self.assertFalse(self.manager.detect("web", "tenant-a")["ready"])

    def test_executable_preview_blocked_in_all_environments_without_bypass(self):
        self.make_package()
        binary = self.root / "node_modules" / "next" / "dist" / "bin" / "next"
        binary.parent.mkdir(parents=True)
        binary.write_text("throw Error('must not execute')", encoding="utf-8")
        info = self.manager.detect("web", "tenant-a")
        self.assertTrue(info["dependencies_ready"])
        self.assertFalse(info["ready"])
        self.assertEqual(info["isolation_status"], "unavailable")
        for environment in ("development", "production", "prod", "test", ""):
            for override in ("", "1", "true", "yes"):
                with self.subTest(environment=environment, override=override):
                    with patch.object(self.manager.executor, "start", side_effect=PreviewLifecycleError("fixture: isolation unavailable")), patch.dict(os.environ, {"OLYMPUS_ENV": environment, "OLYMPUS_ALLOW_UNSANDBOXED_PREVIEW": override}), patch(
                        "olympus.cloud.project_studio.subprocess.Popen"
                    ) as popen:
                        with self.assertRaisesRegex(RuntimeError, "executor isolado"):
                            self.manager.start("web", "tenant-a")
                        popen.assert_not_called()
        self.assertIsNone(self.manager.get("web", "tenant-a"))
        self.assertEqual(self.manager.logs("web", "tenant-a"), [])

    def test_blocked_runtime_preserves_tenant_access_boundary(self):
        self.make_package()
        with patch("olympus.cloud.project_studio.subprocess.Popen") as popen:
            with self.assertRaises(KeyError):
                self.manager.start("web", "tenant-b")
            popen.assert_not_called()

    def test_logs_are_bounded_and_secrets_are_redacted(self):
        process = FakeProcess()
        session = RuntimeSession("safe", "web", "tenant-a", "Next.js", str(self.root), 3001, "running", 1, 9999999999, process)
        self.manager._sessions[session.token] = session
        self.manager._project_tokens[("tenant-a", "web")] = session.token
        for index in range(1100):
            self.manager._append_log("safe", "runtime", "TOKEN=secret-%s" % index)
        logs = self.manager.logs("web", "tenant-a")
        self.assertEqual(len(logs), 1000)
        self.assertTrue(all("secret-" not in item.message for item in logs))

    def test_runtime_rewriter_injects_visual_selector_and_scopes_assets(self):
        body = b'<html><body><script src="/_next/app.js"></script></body></html>'
        rewritten = self.manager.rewrite_text("capability", "text/html", body).decode("utf-8")
        self.assertIn('/cloud/projects/_runtime/capability/_next/app.js', rewritten)
        self.assertIn("olympus-element-selected", rewritten)
        self.assertIn("olympus-inspect-mode", rewritten)

    def test_proxy_rejects_parent_path_segments(self):
        process = FakeProcess()
        session = RuntimeSession("safe", "web", "tenant-a", "Next.js", str(self.root), 3001, "running", 1, 9999999999, process)
        self.manager._sessions[session.token] = session
        self.manager._project_tokens[("tenant-a", "web")] = session.token
        with self.assertRaises(ValueError):
            self.manager.proxy("safe", "../private")

    def test_project_javascript_cannot_write_host_marker(self):
        self.make_package()
        marker = Path(self.temporary.name) / "host-marker"
        binary = self.root / "node_modules" / "next" / "dist" / "bin" / "next"
        binary.parent.mkdir(parents=True)
        binary.write_text("require('fs').writeFileSync(" + json.dumps(str(marker)) + ", 'executed');", encoding="utf-8")
        original = binary.read_bytes()
        # No subprocess mock: exercise the production start path directly.
        # Docker availability changes the failure reason for this intentionally
        # incomplete app; both paths must preserve the host and original binary.
        with self.assertRaises(RuntimeError) as blocked:
            self.manager.start("web", "tenant-a")
        self.assertIn(str(blocked.exception), {
            PREVIEW_ISOLATION_MESSAGE,
            "O preview isolado não confirmou uma página HTTP dentro do prazo.",
        })
        self.assertFalse(marker.exists())
        self.assertEqual(binary.read_bytes(), original)
        self.assertIsNone(self.manager.get("web", "tenant-a"))


class ProjectStudioContractTests(unittest.TestCase):
    def test_http_contract_exposes_editor_runtime_console_and_proxy(self):
        root = Path(__file__).resolve().parents[1]
        api = Path(root, "backend", "app", "api", "cloud_projects.py").read_text(encoding="utf-8")
        for route in ('/{project_id}/files', '/{project_id}/file', '/{project_id}/runtime', '/{project_id}/runtime/logs', '/_runtime/{token}/{asset_path:path}'):
            self.assertIn(route, api)
        self.assertIn("_RUNTIME.project_is_busy", api)
        self.assertIn("_STUDIO_RUNTIMES.stop", api)


if __name__ == "__main__":
    unittest.main()
