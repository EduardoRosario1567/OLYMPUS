"""Regression checks for restricted static delivery (stdlib only)."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verificar_entrega_estatica.py"
spec = importlib.util.spec_from_file_location("delivery_static", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StaticDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "entregas"
        self.site = self.root / "rosales-cafe"
        self.site.mkdir(parents=True)

    def check(self):
        return module.verify(str(self.site), str(self.root))[0]

    def test_valid_static_html(self):
        (self.site / "index.html").write_text("<!doctype html><title>Rosales Café</title>", encoding="utf8")
        self.assertEqual(self.check(), [])

    def test_missing_index(self):
        self.assertTrue(self.check())

    def test_reject_backend_file(self):
        (self.site / "index.html").write_text("ok")
        (self.site / "launch.py").write_text("print('unsafe')")
        self.assertIn("Extensao nao permitida: launch.py", self.check())

    def test_reject_external_resource(self):
        (self.site / "index.html").write_text('<script src="https://example.com/x.js"></script>')
        self.assertTrue(any("Recurso externo" in issue for issue in self.check()))

    def test_reject_eval_js(self):
        (self.site / "index.html").write_text("ok")
        (self.site / "app.js").write_text("eval('1')")
        self.assertTrue(any("Execucao dinamica" in issue for issue in self.check()))

    def test_reject_external_css_resource(self):
        (self.site / "index.html").write_text("<link rel='stylesheet' href='theme.css'>")
        (self.site / "theme.css").write_text('body { background: url("https://remote.example/background.png"); }')
        self.assertTrue(any("CSS externo" in issue for issue in self.check()))

    def test_reject_external_javascript_fetch(self):
        (self.site / "index.html").write_text("<script src='app.js'></script>")
        (self.site / "app.js").write_text('fetch("https://remote.example/tracker")')
        self.assertTrue(any("JS externo" in issue for issue in self.check()))

    def test_reject_symlink(self):
        (self.site / "index.html").write_text("ok")
        (self.site / "outside.txt").symlink_to(Path(self.temp.name))
        self.assertTrue(any("proibido" in issue for issue in self.check()))

    def test_reject_outside_root(self):
        self.assertTrue(module.verify(self.temp.name, self.root)[0])


if __name__ == "__main__":
    unittest.main()
