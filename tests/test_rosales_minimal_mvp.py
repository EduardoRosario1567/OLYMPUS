"""Deterministic static Rosales MVP contract, independent of external providers."""
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from olympus.cloud.project_templates import INDEX_HTML, STYLE_CSS, TEMPLATE_ID, write_rosales_mvp
from olympus.cloud.project_workspace import ProjectWorkspaceManager
from olympus.cloud.project_preview import ProjectPreviewSessions

class RosalesMinimalPilotTests(unittest.TestCase):
    def test_static_safe_and_no_broken_navigation(self):
        self.assertEqual(TEMPLATE_ID, "rosales_cafe_mvp")
        self.assertIn('lang="pt-BR"', INDEX_HTML)
        self.assertIn('name="viewport"', INDEX_HTML)
        self.assertIn("Rosales Café", INDEX_HTML)
        self.assertIn("@media(max-width:760px)", STYLE_CSS)
        ids=set(re.findall(r'\bid="([^"]+)"', INDEX_HTML))
        links=set(re.findall(r'href="#([^"]+)"', INDEX_HTML))
        self.assertTrue(links)
        self.assertFalse(links-ids)
        for unsafe in ("<script", "https://", "http://", "mailto:", "tel:",
                       "Fundado por", "sustentabilidade", "desde 19"):
            self.assertNotIn(unsafe.lower(), INDEX_HTML.lower())
        self.assertNotIn("@import", STYLE_CSS.lower())
        self.assertNotIn("url(", STYLE_CSS.lower())

    def test_preview_export_restart_tenant_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=ProjectWorkspaceManager(folder)
            a=manager.create("Rosales Café — mínimo", tenant_id="tenant-a")
            hashes=write_rosales_mvp(manager.project_root(a.project_id,tenant_id="tenant-a"))
            self.assertEqual({"index.html","style.css"},set(hashes))
            self.assertTrue(all(len(x)==64 for x in hashes.values()))
            with self.assertRaises(ValueError):
                write_rosales_mvp(manager.project_root(a.project_id,tenant_id="tenant-a"))
            with self.assertRaises(KeyError):
                manager.project_root(a.project_id,tenant_id="tenant-b")
            self.assertEqual([],manager.list(tenant_id="tenant-b"))
            preview=ProjectPreviewSessions(manager)
            session=preview.create(a.project_id,tenant_id="tenant-a")
            self.assertEqual("index.html",session.entrypoint)
            self.assertEqual(INDEX_HTML,preview.resolve(session.token)[1].read_text(encoding="utf-8"))
            with zipfile.ZipFile(manager.export_zip(a.project_id,tenant_id="tenant-a")) as archive:
                self.assertEqual({"index.html","style.css"},set(archive.namelist()))
                self.assertEqual(INDEX_HTML.encode(),archive.read("index.html"))
            restarted=ProjectWorkspaceManager(folder)
            self.assertEqual(a.project_id,restarted.list(tenant_id="tenant-a")[0].project_id)
            self.assertEqual(INDEX_HTML,(restarted.project_root(a.project_id,tenant_id="tenant-a")/"index.html").read_text(encoding="utf-8"))

    def test_api_template_allowlist(self):
        backend=str(ROOT/"backend")
        if backend not in sys.path: sys.path.insert(0,backend)
        try:
            from app.api.cloud_projects import ProjectCreate
        except ImportError as error:
            self.skipTest("Backend dependencies unavailable: "+str(error))
        self.assertEqual(TEMPLATE_ID, ProjectCreate(name="Rosales",template=TEMPLATE_ID).template)
        with self.assertRaises(ValueError):
            ProjectCreate(name="X",template="../danger")

if __name__=="__main__":
    unittest.main()
