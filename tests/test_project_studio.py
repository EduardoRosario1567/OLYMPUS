import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.cloud.project_studio import ProjectFileEditor, ProjectRuntimeManager, RuntimeSession
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

    def test_starts_recognized_runtime_without_shell_and_reuses_session(self):
        self.make_package()
        binary = self.root / "node_modules" / "next" / "dist" / "bin" / "next"
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
        process = FakeProcess()
        with patch("olympus.cloud.project_studio.shutil.which", return_value="/usr/bin/node"), patch(
            "olympus.cloud.project_studio.subprocess.Popen", return_value=process
        ) as popen, patch.object(self.manager, "_listening", return_value=True):
            first = self.manager.start("web", "tenant-a")
            second = self.manager.start("web", "tenant-a")
        self.assertEqual(first.token, second.token)
        self.assertEqual(first.status, "running")
        self.assertFalse(popen.call_args.kwargs.get("shell", False))
        self.assertEqual(popen.call_args.args[0][0], "/usr/bin/node")
        self.assertEqual(popen.call_args.kwargs["cwd"], str(self.root))
        environment = popen.call_args.kwargs["env"]
        self.assertNotIn("OLYMPUS_JWT_SECRET", environment)

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

    def test_real_local_runtime_starts_proxies_and_stops_without_dependencies(self):
        if not shutil.which("node"):
            self.skipTest("Node.js unavailable")
        self.make_package()
        binary = self.root / "node_modules" / "next" / "dist" / "bin" / "next"
        binary.parent.mkdir(parents=True)
        binary.write_text(
            "const http=require('http');"
            "const a=process.argv;const i=a.indexOf('--port');const p=Number(a[i+1]);"
            "http.createServer((q,r)=>{r.setHeader('Content-Type','text/html');"
            "r.end('<html><body><main id=app>Runtime real</main></body></html>')}).listen(p,'127.0.0.1');",
            encoding="utf-8",
        )
        session = self.manager.start("web", "tenant-a")
        try:
            status, headers, body = self.manager.proxy(session.token)
            self.assertEqual(status, 200)
            self.assertIn("text/html", headers["Content-Type"])
            self.assertIn(b"Runtime real", body)
            self.assertIn(b"olympus-element-selected", body)
            self.assertTrue(self.manager.get("web", "tenant-a"))
        finally:
            self.assertTrue(self.manager.stop("web", "tenant-a"))
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
