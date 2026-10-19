import tempfile
import unittest
from pathlib import Path

from olympus.cloud.project_templates import INDEX_HTML, STYLE_CSS, write_rosales_mvp
from olympus.cloud.project_workspace import ProjectWorkspaceManager
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.rosales_ai import RosalesAIError, validate_static_files, save_generated_files, pilot_generation_guard


class TestRosalesAIPilot(unittest.TestCase):
    def test_valid_template(self):
        hashes = validate_static_files(INDEX_HTML, STYLE_CSS)
        self.assertEqual(set(hashes), {"index.html", "style.css"})

    def test_unsafe_markup_is_rejected(self):
        cases = [
            INDEX_HTML.replace("</body>", "<script>alert(1)</script></body>"),
            INDEX_HTML.replace('href="#conceito"', 'href="https://example.test"'),
            INDEX_HTML.replace('href="#conceito"', 'href="#inexistente"'),
            INDEX_HTML.replace('id="conceito"', 'id="inicio"'),
            INDEX_HTML.replace('lang="pt-BR"', 'lang="en"'),
            INDEX_HTML.replace('class="hero"', 'class="hero" onclick="evil()"'),
        ]
        for item in cases:
            with self.subTest(change=item[:95]), self.assertRaises(RosalesAIError):
                validate_static_files(item, STYLE_CSS)

    def test_unverified_business_claims_are_rejected(self):
        added = INDEX_HTML.replace(
            "</body>",
            "<p>Trabalhamos com produtores sustentáveis e oferecemos Wi-Fi gratuito.</p></body>",
        )
        with self.assertRaisesRegex(RosalesAIError, "not approved"):
            validate_static_files(added, STYLE_CSS)
        css_claim = STYLE_CSS + "\\n.fake:after{content:'Baristas certificados';}"
        with self.assertRaisesRegex(RosalesAIError, "Unapproved CSS"):
            validate_static_files(INDEX_HTML, css_claim)

    def test_remote_css_is_rejected(self):
        for tail in ('@import "remote.css";','.x{background:url(remote.png)}',
                     '@font-face{src:local(font)}', '.x{behavior:url(x)}',
                     '@namespace "https://invalid.example";',
                     '@\\69mport "https://invalid.example";'):
            with self.subTest(tail=tail), self.assertRaises(RosalesAIError):
                validate_static_files(INDEX_HTML, STYLE_CSS + tail)

    def test_save_preview_restart_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            projects = ProjectWorkspaceManager(directory)
            record = projects.create("Rosales Café — MVP de validação", tenant_id="a")
            root = projects.project_root(record.project_id, tenant_id="a")
            write_rosales_mvp(root)
            edited = INDEX_HTML.replace("aprecia o momento.", "transforma o momento.")
            changed_css = STYLE_CSS + "\n/* validated */"
            result = save_generated_files(root, edited, changed_css)
            self.assertEqual(set(result), {"index.html", "style.css"})
            with self.assertRaises(RosalesAIError):
                save_generated_files(root, edited, changed_css)
            preview = ProjectPreviewSessions(projects).create(record.project_id, tenant_id="a")
            self.assertEqual(preview.entrypoint, "index.html")
            restarted = ProjectWorkspaceManager(directory)
            self.assertIn("transforma o momento.", (restarted.project_root(record.project_id, tenant_id="a") / "index.html").read_text("utf-8"))
            with self.assertRaises(KeyError):
                restarted.project_root(record.project_id, tenant_id="b")

    def test_rate_limit_on_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            with pilot_generation_guard(Path(directory), "tenant", "project"):
                pass
            with self.assertRaises(RosalesAIError):
                with pilot_generation_guard(Path(directory), "tenant", "project"):
                    pass
