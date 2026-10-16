import tempfile
import unittest
from pathlib import Path

from olympus.cloud.project_preview import ProjectPreviewSessions
from scripts.preserve_static_delivery import preserve_validated_site


class TenantProjects:
    def __init__(self, root):
        self.root = root

    def project_root(self, project_id, tenant_id="local"):
        if project_id != "rosales-project" or tenant_id != "tenant-a":
            raise KeyError("not in tenant")
        return self.root


class VerifiedArtifactPreviewTests(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        self.root = Path(context.name)
        project_root = self.root / "owned-project"
        project_root.mkdir()
        self.project_root = project_root
        self.preview = ProjectPreviewSessions(TenantProjects(project_root))
        self.workspace = self.root / "mission"
        (self.workspace / "site").mkdir(parents=True)
        (self.workspace / "site" / "index.html").write_text(
            '<!DOCTYPE html><html><title>Rosales Café</title>'
            '<link href="/assets/style.css" rel="stylesheet">'
            '<body>Rosales Café</body></html>', encoding="utf-8"
        )
        (self.workspace / "site" / "assets").mkdir()
        (self.workspace / "site" / "assets" / "style.css").write_text("body{color:#432b1a}")
        (self.workspace / "site" / "assets" / "config.json").write_text('{"theme":"coffee"}')
        self.build_id = "rosales-verifiable-1"
        preserve_validated_site(
            self.workspace, self.project_root / ".olympus" / "web_builds", self.build_id
        )
        self.artifact = self.project_root / ".olympus" / "web_builds" / self.build_id

    def test_preview_session_resolves_verified_artifact_and_assets(self):
        session = self.preview.create_verified_artifact(
            "rosales-project", self.build_id, tenant_id="tenant-a"
        )
        result, path = self.preview.resolve(session.token)
        self.assertEqual(result.entrypoint, "index.html")
        self.assertEqual(path.name, "index.html")
        _, css = self.preview.resolve(session.token, "assets/style.css")
        self.assertEqual(css.read_text(), "body{color:#432b1a}")
        _, data = self.preview.resolve(session.token, "assets/config.json")
        self.assertIn("coffee", data.read_text())
        html = self.preview.rewrite_text(session.token, ".html", path.read_text())
        self.assertIn("/cloud/projects/_preview/" + session.token + "/assets/style.css", html)

    def test_integrity_change_before_session_is_rejected(self):
        (self.artifact / "site" / "index.html").write_text("changed")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.preview.create_verified_artifact(
                "rosales-project", self.build_id, tenant_id="tenant-a"
            )

    def test_integrity_change_after_session_is_rejected(self):
        session = self.preview.create_verified_artifact(
            "rosales-project", self.build_id, tenant_id="tenant-a"
        )
        (self.artifact / "site" / "assets" / "style.css").write_text("body{color:red}")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.preview.resolve(session.token, "assets/style.css")

    def test_wrong_tenant_or_build_path_is_blocked(self):
        with self.assertRaises(KeyError):
            self.preview.create_verified_artifact(
                "rosales-project", self.build_id, tenant_id="tenant-b"
            )
        for value in ("../evil", "x/y", "", ".hidden"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.preview.create_verified_artifact(
                        "rosales-project", value, tenant_id="tenant-a"
                    )

    def test_missing_manifest_and_symlink_are_rejected(self):
        (self.artifact / "manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.preview.create_verified_artifact(
                "rosales-project", self.build_id, tenant_id="tenant-a"
            )
        (self.artifact / "site" / "assets" / "link.css").symlink_to(
            self.artifact / "site" / "assets" / "style.css"
        )
        with self.assertRaises(ValueError):
            self.preview._resolve_asset(self.artifact / "site", "assets/link.css")


if __name__ == "__main__":
    unittest.main()
