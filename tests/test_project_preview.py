import tempfile
import time
import unittest
from pathlib import Path

from olympus.cloud.project_preview import PreviewSession, ProjectPreviewSessions
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class ProjectPreviewSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.projects = ProjectWorkspaceManager(self.temporary.name)
        self.project = self.projects.create("Site", "site", tenant_id="tenant-a")
        self.root = Path(self.project.root)
        self.previews = ProjectPreviewSessions(self.projects, ttl_seconds=30)

    def test_preview_serves_only_web_assets_from_the_same_project(self):
        Path(self.root, "index.html").write_text('<link rel="stylesheet" href="style.css">', encoding="utf-8")
        Path(self.root, "style.css").write_text("body{}", encoding="utf-8")
        session = self.previews.create("site", tenant_id="tenant-a")
        _, entry = self.previews.resolve(session.token)
        _, asset = self.previews.resolve(session.token, "style.css")
        self.assertEqual(entry.name, "index.html")
        self.assertEqual(asset.name, "style.css")

    def test_preview_blocks_secrets_source_files_and_traversal(self):
        Path(self.root, "index.html").write_text("ok", encoding="utf-8")
        Path(self.root, ".env").write_text("SECRET=x", encoding="utf-8")
        Path(self.root, "server.py").write_text("secret", encoding="utf-8")
        Path(self.root, "data.json").write_text('{"secret":true}', encoding="utf-8")
        Path(self.root, "attachments").mkdir()
        Path(self.root, "attachments", "uploaded.html").write_text("private", encoding="utf-8")
        session = self.previews.create("site", tenant_id="tenant-a")
        for unsafe in (".env", "server.py", "data.json", "attachments/uploaded.html", "../index.html"):
            with self.assertRaises((ValueError, KeyError)):
                self.previews.resolve(session.token, unsafe)

    def test_preview_requires_html_and_expires(self):
        with self.assertRaisesRegex(ValueError, "no HTML"):
            self.previews.create("site", tenant_id="tenant-a")
        Path(self.root, "index.html").write_text("ok", encoding="utf-8")
        session = self.previews.create("site", tenant_id="tenant-a")
        self.previews._sessions[session.token] = PreviewSession(
            session.token, session.project_id, session.tenant_id, session.entrypoint, time.time() - 1
        )
        with self.assertRaises(KeyError):
            self.previews.resolve(session.token)

    def test_tenant_isolation_is_checked_when_session_is_created(self):
        Path(self.root, "index.html").write_text("ok", encoding="utf-8")
        with self.assertRaises(KeyError):
            self.previews.create("site", tenant_id="tenant-b")

    def test_root_relative_html_and_css_assets_stay_inside_preview_session(self):
        html = '<link href="/assets/app.css"><img src="/images/logo.svg"><a href="https://example.com">fora</a>'
        rewritten = self.previews.rewrite_text("secure-token", ".html", html)
        self.assertIn('href="/cloud/projects/_preview/secure-token/assets/app.css"', rewritten)
        self.assertIn('src="/cloud/projects/_preview/secure-token/images/logo.svg"', rewritten)
        self.assertIn('href="https://example.com"', rewritten)
        css = self.previews.rewrite_text("secure-token", ".css", "body{background:url('/images/bg.png')}")
        self.assertIn("url('/cloud/projects/_preview/secure-token/images/bg.png')", css)


if __name__ == "__main__":
    unittest.main()
