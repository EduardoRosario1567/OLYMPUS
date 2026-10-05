import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.cloud.github_integration import (
    GitHubApi,
    GitHubApiError,
    GitHubIntegrationService,
    RepositoryBinding,
)
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class FakeGitHubApi:
    def __init__(self):
        self.calls = []
        self.blob = 0
        self.pages_exists = False
        self.remote_tree = []
        self.fail_ref_update = False

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/user":
            return {"login": "fernando", "name": "Fernando", "avatar_url": "https://example/avatar"}
        if method == "GET" and path == "/repos/fernando/demo":
            return {
                "owner": {"login": "fernando"}, "default_branch": "main",
                "html_url": "https://github.com/fernando/demo", "private": False,
                "permissions": {"push": True},
            }
        if method == "POST" and path == "/user/repos":
            return {
                "owner": {"login": "fernando"}, "default_branch": "main",
                "html_url": "https://github.com/fernando/%s" % payload["name"],
                "private": bool(payload["private"]),
            }
        if method == "GET" and "/git/ref/heads/olympus-pages" in path:
            if not self.pages_exists:
                raise GitHubApiError(404, "Not Found")
            return {"object": {"sha": "pages-head"}}
        if method == "GET" and "/git/ref/heads/" in path:
            return {"object": {"sha": "head-one"}}
        if method == "GET" and "/git/commits/head-one" in path:
            return {"tree": {"sha": "tree-one"}}
        if method == "GET" and "/git/trees/tree-one?recursive=1" in path:
            return {"tree": self.remote_tree, "truncated": False}
        if method == "POST" and path.endswith("/git/blobs"):
            self.blob += 1
            return {"sha": "blob-%s" % self.blob}
        if method == "POST" and path.endswith("/git/trees"):
            return {"sha": "tree-new"}
        if method == "POST" and path.endswith("/git/commits"):
            return {"sha": "commit-new", "html_url": "https://github.com/fernando/demo/commit/commit-new"}
        if method == "PATCH" and "/git/refs/heads/" in path:
            if self.fail_ref_update:
                raise GitHubApiError(409, "Reference update failed")
            return {"object": {"sha": payload["sha"]}}
        if method == "POST" and path.endswith("/git/refs"):
            self.pages_exists = True
            return {"object": {"sha": payload["sha"]}}
        if method == "GET" and path.endswith("/pages/builds/latest"):
            return {"status": "built", "error": {"message": None}}
        if method == "GET" and path.endswith("/pages"):
            if not self.pages_exists:
                raise GitHubApiError(404, "Not Found")
            return {"html_url": "https://fernando.github.io/demo/", "status": "built"}
        if method == "POST" and path.endswith("/pages"):
            self.pages_exists = True
            return {"html_url": "https://fernando.github.io/demo/", "status": "queued"}
        if method == "PUT" and path.endswith("/pages"):
            return {}
        if method == "POST" and path.endswith("/pages/builds"):
            return {"status": "queued"}
        if method == "GET" and "/commits?" in path:
            return [{
                "sha": "abc123", "html_url": "https://github.com/fernando/demo/commit/abc123",
                "commit": {"message": "Entrega", "author": {"name": "Fernando", "date": "2026-09-08T12:00:00Z"}},
            }]
        raise AssertionError("unexpected GitHub call: %s %s %r" % (method, path, payload))


class FakeHttpResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.content


class GitHubApiClientTests(unittest.TestCase):
    def test_client_uses_fixed_origin_version_and_bearer_header(self):
        token = "github_pat_" + "z" * 40
        with patch("olympus.cloud.github_integration.urlopen", return_value=FakeHttpResponse(b'{"login":"safe"}')) as opened:
            result = GitHubApi(token).request("GET", "/user")
        request = opened.call_args.args[0]
        self.assertEqual(result["login"], "safe")
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
        self.assertEqual(request.get_header("X-github-api-version"), "2026-03-10")

    def test_client_rejects_origin_and_header_injection(self):
        api = GitHubApi("github_pat_" + "z" * 40)
        for path in ("https://evil.example", "//evil.example", "/user\x00bad"):
            with self.assertRaises(ValueError):
                api.request("GET", path)


class GitHubIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.projects = ProjectWorkspaceManager(str(self.base / "cloud"))
        self.project = self.projects.create("Demo", "demo", tenant_id="tenant-a")
        self.root = Path(self.project.root)
        self.fake = FakeGitHubApi()
        self.service = GitHubIntegrationService(
            self.projects,
            self.base / "integrations",
            api_factory=lambda _token: self.fake,
        )
        self.token = "github_pat_" + "a" * 40

    def connect_and_link(self):
        account = self.service.connect("tenant-a", self.token)
        self.assertEqual(account.login, "fernando")
        return self.service.link_repository("demo", "tenant-a", "fernando", "demo")

    def test_token_is_session_only_and_never_persisted(self):
        binding = self.connect_and_link()
        self.assertEqual(binding.branch, "main")
        stored = (self.base / "integrations" / "github-bindings.json").read_text(encoding="utf-8")
        self.assertNotIn(self.token, stored)
        self.assertNotIn("github_pat_", stored)
        self.assertEqual(oct((self.base / "integrations" / "github-bindings.json").stat().st_mode & 0o777), "0o600")
        reloaded = GitHubIntegrationService(self.projects, self.base / "integrations", api_factory=lambda _token: self.fake)
        status = reloaded.status("demo", "tenant-a")
        self.assertIsNone(status["account"])
        self.assertEqual(status["binding"].repo, "demo")

    def test_tenant_isolation_and_safe_names(self):
        self.service.connect("tenant-a", self.token)
        with self.assertRaises(KeyError):
            self.service.status("demo", "tenant-b")
        for unsafe in ("../repo", "owner/repo", ".", "bad name"):
            with self.assertRaises(ValueError):
                self.service.link_repository("demo", "tenant-a", "fernando", unsafe)
        for unsafe in ("../main", "refs/heads/main", "bad branch", "main.lock"):
            with self.assertRaises(ValueError):
                self.service._branch(unsafe)

    def test_failed_repository_validation_does_not_persist_binding(self):
        self.service.connect("tenant-a", self.token)
        with patch.object(self.service, "_reference", side_effect=GitHubApiError(404, "missing branch")):
            with self.assertRaises(GitHubApiError):
                self.service.link_repository("demo", "tenant-a", "fernando", "demo", "missing")
        self.assertIsNone(self.service.bindings.get("demo", "tenant-a"))

    def test_sync_creates_one_atomic_fast_forward_commit_without_secrets(self):
        (self.root / "index.html").write_text("<h1>Olympus</h1>", encoding="utf-8")
        (self.root / "asset.bin").write_bytes(b"\x00\x01")
        (self.root / ".env").write_text("TOKEN=never", encoding="utf-8")
        (self.root / "attachments").mkdir()
        (self.root / "attachments" / "private.txt").write_text("private", encoding="utf-8")
        self.connect_and_link()
        result = self.service.sync("demo", "tenant-a", "Primeira entrega\nsegura")
        self.assertEqual(result.files_changed, 2)
        self.assertFalse(result.unchanged)
        tree_call = next(call for call in self.fake.calls if call[0] == "POST" and call[1].endswith("/git/trees"))
        self.assertEqual(tree_call[2]["base_tree"], "tree-one")
        self.assertEqual({item["path"] for item in tree_call[2]["tree"]}, {"asset.bin", "index.html"})
        ref_call = next(call for call in self.fake.calls if call[0] == "PATCH" and "/git/refs/heads/main" in call[1])
        self.assertIs(ref_call[2]["force"], False)
        serialized_calls = json.dumps(self.fake.calls)
        self.assertNotIn("TOKEN=never", serialized_calls)
        self.assertNotIn("private", serialized_calls)

    def test_sync_blocks_files_reached_through_directory_symlink(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "leak.txt").write_text("secret", encoding="utf-8")
        try:
            (self.root / "linked").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symbolic links unavailable")
        (self.root / "index.html").write_text("safe", encoding="utf-8")
        files = self.service._project_files(self.root.resolve())
        self.assertEqual([path for path, _, _ in files], ["index.html"])

    def test_unchanged_sync_does_not_create_commit(self):
        content = b"same"
        (self.root / "index.html").write_bytes(content)
        self.fake.remote_tree = [{"path": "index.html", "type": "blob", "sha": self.service._git_blob_sha(content)}]
        self.connect_and_link()
        result = self.service.sync("demo", "tenant-a")
        self.assertTrue(result.unchanged)
        self.assertFalse(any(call[0] == "POST" and call[1].endswith("/git/commits") for call in self.fake.calls))

    def test_remote_conflict_never_forces_or_records_commit(self):
        (self.root / "index.html").write_text("new", encoding="utf-8")
        self.connect_and_link()
        self.fake.fail_ref_update = True
        with self.assertRaisesRegex(GitHubApiError, "Reference"):
            self.service.sync("demo", "tenant-a")
        self.assertIsNone(self.service.bindings.get("demo", "tenant-a").last_commit_sha)
        patch_call = next(call for call in self.fake.calls if call[0] == "PATCH" and "/git/refs/heads/main" in call[1])
        self.assertIs(patch_call[2]["force"], False)

    def test_publish_uses_dedicated_branch_and_rewrites_root_assets(self):
        app = self.root / "app"
        app.mkdir()
        (app / "index.html").write_text('<link href="/style.css"><h1>Site</h1>', encoding="utf-8")
        (app / "style.css").write_text("body{background:url('/hero.png')}", encoding="utf-8")
        (app / "hero.png").write_bytes(b"png")
        (app / "source.py").write_text("not public", encoding="utf-8")
        self.connect_and_link()
        result = self.service.publish("demo", "tenant-a")
        self.assertEqual(result.branch, "olympus-pages")
        self.assertEqual(result.files_published, 3)
        ref = next(call for call in self.fake.calls if call[0] == "POST" and call[1].endswith("/git/refs"))
        self.assertEqual(ref[2]["ref"], "refs/heads/olympus-pages")
        publish_tree = [call for call in self.fake.calls if call[0] == "POST" and call[1].endswith("/git/trees")][-1]
        self.assertEqual({item["path"] for item in publish_tree[2]["tree"]}, {"index.html", "style.css", "hero.png"})
        blobs = [call[2]["content"] for call in self.fake.calls if call[0] == "POST" and call[1].endswith("/git/blobs")][-3:]
        decoded = "\n".join(base64_decode(value) for value in blobs)
        self.assertIn('/demo/style.css', decoded)
        self.assertIn('/demo/hero.png', decoded)
        self.assertEqual(self.service.publication_status("demo", "tenant-a")["status"], "built")

    def test_private_repository_cannot_use_free_pages_path(self):
        (self.root / "index.html").write_text("ok", encoding="utf-8")
        self.service.connect("tenant-a", self.token)
        private = RepositoryBinding("demo", "tenant-a", "fernando", "demo", "main", "url", True, True, 1, 1)
        self.service.bindings.put(private)
        with self.assertRaisesRegex(ValueError, "público"):
            self.service.publish("demo", "tenant-a")

    def test_publish_rejects_non_utf8_markup(self):
        (self.root / "index.html").write_bytes(b"\xff\xfe")
        self.connect_and_link()
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.service.publish("demo", "tenant-a")

    def test_auto_sync_requires_live_session_credential(self):
        (self.root / "index.html").write_text("ok", encoding="utf-8")
        self.connect_and_link()
        self.service.disconnect("tenant-a")
        self.assertIsNone(self.service.auto_sync("demo", "tenant-a", "Auto"))

    def test_create_repository_branch_and_commit_history(self):
        self.service.connect("tenant-a", self.token)
        binding = self.service.create_repository("demo", "tenant-a", "demo", private=False)
        self.assertEqual(binding.owner, "fernando")
        branch = self.service.create_branch("demo", "tenant-a", "olympus/design")
        self.assertEqual(branch.branch, "olympus/design")
        commits = self.service.commits("demo", "tenant-a")
        self.assertEqual(commits[0]["message"], "Entrega")


def base64_decode(value):
    import base64
    try:
        return base64.b64decode(value).decode("utf-8")
    except UnicodeDecodeError:
        return "<binary>"


class GitHubContractTests(unittest.TestCase):
    def test_backend_routes_are_tenant_scoped_and_never_return_tokens(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "backend" / "app" / "api" / "github.py").read_text(encoding="utf-8")
        for route in ("/connection", "/repositories", "/repository", "/branches", "/sync", "/commits", "/publish", "/publication"):
            self.assertIn(route, source)
        self.assertIn("identity.tenant_id", source)
        self.assertNotIn('"token": payload.token', source)


if __name__ == "__main__":
    unittest.main()
