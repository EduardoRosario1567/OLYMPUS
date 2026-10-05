from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import base64
import json
import os
import re
import tempfile
import time

from .project_workspace import ProjectWorkspaceManager


GITHUB_API_VERSION = "2026-03-10"
MAX_GITHUB_FILE_BYTES = 20 * 1024 * 1024
MAX_GITHUB_PROJECT_BYTES = 200 * 1024 * 1024
MAX_GITHUB_FILES = 5000
MAX_API_RESPONSE_BYTES = 20 * 1024 * 1024
PAGES_BRANCH = "olympus-pages"

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_BRANCH = re.compile(r"^(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]{1,128}(?<![./])$")
_PROTECTED_ROOTS = {
    ".executions", ".git", ".next", ".olympus", "attachments", "imports",
    "node_modules", "coverage",
}
_PROTECTED_NAMES = {".olympus-attachments.json", ".DS_Store"}
_PUBLISH_EXTENSIONS = {
    ".avif", ".css", ".gif", ".htm", ".html", ".ico", ".jpeg", ".jpg",
    ".js", ".json", ".mjs", ".mp4", ".png", ".svg", ".ttf", ".webm",
    ".webp", ".woff", ".woff2",
}
_STATIC_ENTRYPOINTS = ("index.html", "app/index.html", "public/index.html", "dist/index.html", "build/index.html")


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)


class GitHubApi:
    """Small GitHub REST client with fixed origin, bounded responses and no logs."""

    def __init__(self, token: str, timeout_seconds: int = 20) -> None:
        clean = str(token or "").strip()
        if len(clean) < 20 or len(clean) > 512 or any(char in clean for char in "\r\n\x00"):
            raise ValueError("Token do GitHub inválido.")
        self._token = clean
        self.timeout_seconds = max(3, min(60, int(timeout_seconds)))

    def request(self, method: str, path: str, payload: Optional[dict] = None) -> object:
        if not path.startswith("/") or path.startswith("//") or "://" in path or "\x00" in path:
            raise ValueError("Caminho da API do GitHub inválido.")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            "https://api.github.com" + path,
            data=body,
            method=method.upper(),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json",
                "User-Agent": "OLYMPUS-Professional/2.0",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read(MAX_API_RESPONSE_BYTES + 1)
                if len(content) > MAX_API_RESPONSE_BYTES:
                    raise GitHubApiError(502, "A resposta do GitHub excedeu o limite seguro.")
                if not content:
                    return {}
                return json.loads(content.decode("utf-8"))
        except HTTPError as exc:
            content = exc.read(64 * 1024)
            try:
                detail = json.loads(content.decode("utf-8", errors="replace"))
                message = str(detail.get("message") or "Falha na API do GitHub.")
            except (ValueError, AttributeError):
                message = "Falha na API do GitHub."
            raise GitHubApiError(exc.code, message[:500]) from None
        except (URLError, TimeoutError, OSError):
            raise GitHubApiError(503, "Não foi possível alcançar o GitHub.") from None


@dataclass(frozen=True)
class GitHubAccount:
    login: str
    name: str
    avatar_url: str


@dataclass(frozen=True)
class RepositoryBinding:
    project_id: str
    tenant_id: str
    owner: str
    repo: str
    branch: str
    html_url: str
    private: bool
    auto_sync: bool
    connected_at: float
    updated_at: float
    last_commit_sha: Optional[str] = None
    pages_url: Optional[str] = None
    pages_status: Optional[str] = None


@dataclass(frozen=True)
class SyncResult:
    owner: str
    repo: str
    branch: str
    commit_sha: str
    commit_url: str
    files_changed: int
    unchanged: bool


@dataclass(frozen=True)
class PublishResult:
    url: str
    status: str
    branch: str
    commit_sha: str
    files_published: int


class GitHubBindingStore:
    """Persists public repository metadata only; credentials never enter this file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._records = self._load()

    @staticmethod
    def _key(project_id: str, tenant_id: str) -> str:
        return "%s:%s" % (tenant_id, project_id)

    def _load(self) -> dict[str, dict]:
        if not self.path.is_file():
            return {}
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return content if isinstance(content, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".github-bindings-", dir=str(self.path.parent))
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self._records, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def get(self, project_id: str, tenant_id: str) -> Optional[RepositoryBinding]:
        with self._lock:
            value = self._records.get(self._key(project_id, tenant_id))
            if not isinstance(value, dict):
                return None
            try:
                return RepositoryBinding(**value)
            except (TypeError, ValueError):
                return None

    def put(self, binding: RepositoryBinding) -> RepositoryBinding:
        with self._lock:
            self._records[self._key(binding.project_id, binding.tenant_id)] = asdict(binding)
            self._save()
        return binding

    def remove(self, project_id: str, tenant_id: str) -> bool:
        with self._lock:
            removed = self._records.pop(self._key(project_id, tenant_id), None) is not None
            if removed:
                self._save()
            return removed


class GitHubIntegrationService:
    """Tenant-scoped GitHub sync and static Pages publication.

    Synchronization is additive and atomic: it updates local files in one commit,
    never deletes remote-only paths and never force-updates a branch.
    """

    def __init__(
        self,
        projects: ProjectWorkspaceManager,
        data_dir: Path,
        api_factory: Callable[[str], GitHubApi] = GitHubApi,
    ) -> None:
        self.projects = projects
        self.bindings = GitHubBindingStore(Path(data_dir) / "github-bindings.json")
        self.api_factory = api_factory
        self._tokens: dict[str, str] = {}
        self._accounts: dict[str, GitHubAccount] = {}
        self._lock = RLock()

    @staticmethod
    def _name(value: str, label: str) -> str:
        clean = str(value or "").strip()
        if not _NAME.fullmatch(clean) or clean in {".", ".."}:
            raise ValueError("%s inválido." % label)
        return clean

    @staticmethod
    def _branch(value: str) -> str:
        clean = str(value or "").strip()
        if not _BRANCH.fullmatch(clean) or clean.startswith(("-", "refs/")) or clean.endswith(".lock"):
            raise ValueError("Nome de branch inválido.")
        return clean

    @staticmethod
    def _commit_message(value: str) -> str:
        clean = " ".join(str(value or "").replace("\x00", "").split()).strip()
        if not clean:
            clean = "Atualização pelo Olympus"
        return clean[:200]

    def connect(self, tenant_id: str, token: str) -> GitHubAccount:
        api = self.api_factory(token)
        data = api.request("GET", "/user")
        if not isinstance(data, dict) or not data.get("login"):
            raise GitHubApiError(401, "O GitHub não confirmou esta conta.")
        account = GitHubAccount(
            login=str(data["login"])[:100],
            name=str(data.get("name") or data["login"])[:200],
            avatar_url=str(data.get("avatar_url") or "")[:1000],
        )
        with self._lock:
            self._tokens[tenant_id] = str(token).strip()
            self._accounts[tenant_id] = account
        return account

    def disconnect(self, tenant_id: str) -> None:
        with self._lock:
            self._tokens.pop(tenant_id, None)
            self._accounts.pop(tenant_id, None)

    def account(self, tenant_id: str) -> Optional[GitHubAccount]:
        with self._lock:
            return self._accounts.get(tenant_id)

    def _api(self, tenant_id: str) -> GitHubApi:
        with self._lock:
            token = self._tokens.get(tenant_id)
        if not token:
            raise PermissionError("Conecte sua conta do GitHub nesta sessão.")
        return self.api_factory(token)

    def status(self, project_id: str, tenant_id: str) -> dict:
        self.projects.project_root(project_id, tenant_id=tenant_id)
        binding = self.bindings.get(project_id, tenant_id)
        if binding is not None:
            binding = self._binding(project_id, tenant_id)
        return {"account": self.account(tenant_id), "binding": binding}

    def create_repository(self, project_id: str, tenant_id: str, repo: str, private: bool = False) -> RepositoryBinding:
        self.projects.project_root(project_id, tenant_id=tenant_id)
        repo = self._name(repo, "Repositório")
        api = self._api(tenant_id)
        result = api.request("POST", "/user/repos", {
            "name": repo,
            "private": bool(private),
            "auto_init": True,
            "description": "Criado com Olympus",
        })
        if not isinstance(result, dict):
            raise GitHubApiError(502, "Resposta inválida ao criar o repositório.")
        owner = self._name(str((result.get("owner") or {}).get("login") or ""), "Proprietário")
        return self._bind_from_repository(project_id, tenant_id, owner, repo, result)

    def link_repository(self, project_id: str, tenant_id: str, owner: str, repo: str, branch: Optional[str] = None) -> RepositoryBinding:
        self.projects.project_root(project_id, tenant_id=tenant_id)
        owner, repo = self._name(owner, "Proprietário"), self._name(repo, "Repositório")
        api = self._api(tenant_id)
        result = api.request("GET", "/repos/%s/%s" % (quote(owner), quote(repo)))
        if not isinstance(result, dict):
            raise GitHubApiError(502, "Resposta inválida ao conectar o repositório.")
        permissions = result.get("permissions")
        if isinstance(permissions, dict) and not (permissions.get("push") or permissions.get("admin") or permissions.get("maintain")):
            raise PermissionError("A conta conectada não possui permissão de escrita neste repositório.")
        binding = self._bind_from_repository(project_id, tenant_id, owner, repo, result, branch, persist=False)
        self._reference(api, binding.owner, binding.repo, binding.branch)
        return self.bindings.put(binding)

    def _bind_from_repository(
        self,
        project_id: str,
        tenant_id: str,
        owner: str,
        repo: str,
        result: dict,
        branch: Optional[str] = None,
        persist: bool = True,
    ) -> RepositoryBinding:
        now = time.time()
        selected_branch = self._branch(branch or str(result.get("default_branch") or "main"))
        binding = RepositoryBinding(
            project_id=project_id,
            tenant_id=tenant_id,
            owner=owner,
            repo=repo,
            branch=selected_branch,
            html_url=str(result.get("html_url") or "https://github.com/%s/%s" % (owner, repo))[:1000],
            private=bool(result.get("private", False)),
            auto_sync=True,
            connected_at=now,
            updated_at=now,
        )
        return self.bindings.put(binding) if persist else binding

    def unlink_repository(self, project_id: str, tenant_id: str) -> bool:
        self.projects.project_root(project_id, tenant_id=tenant_id)
        return self.bindings.remove(project_id, tenant_id)

    @staticmethod
    def _reference(api: GitHubApi, owner: str, repo: str, branch: str) -> str:
        result = api.request("GET", "/repos/%s/%s/git/ref/heads/%s" % (quote(owner), quote(repo), quote(branch, safe="/")))
        if not isinstance(result, dict) or not isinstance(result.get("object"), dict) or not result["object"].get("sha"):
            raise GitHubApiError(502, "O GitHub não retornou a referência da branch.")
        return str(result["object"]["sha"])

    def create_branch(self, project_id: str, tenant_id: str, branch: str) -> RepositoryBinding:
        binding = self._binding(project_id, tenant_id)
        branch = self._branch(branch)
        api = self._api(tenant_id)
        head = self._reference(api, binding.owner, binding.repo, binding.branch)
        api.request("POST", "/repos/%s/%s/git/refs" % (quote(binding.owner), quote(binding.repo)), {
            "ref": "refs/heads/" + branch,
            "sha": head,
        })
        updated = RepositoryBinding(**{**asdict(binding), "branch": branch, "updated_at": time.time()})
        return self.bindings.put(updated)

    def _binding(self, project_id: str, tenant_id: str) -> RepositoryBinding:
        self.projects.project_root(project_id, tenant_id=tenant_id)
        binding = self.bindings.get(project_id, tenant_id)
        if not binding:
            raise KeyError("Projeto ainda não está conectado a um repositório.")
        if binding.project_id != project_id or binding.tenant_id != tenant_id:
            raise ValueError("Vínculo do GitHub inválido.")
        self._name(binding.owner, "Proprietário")
        self._name(binding.repo, "Repositório")
        self._branch(binding.branch)
        return binding

    @staticmethod
    def _is_protected(relative: Path) -> bool:
        return (
            not relative.parts
            or any(part in _PROTECTED_ROOTS for part in relative.parts)
            or any(part == ".env" or part.startswith(".env.") for part in relative.parts)
            or any(part.startswith(".") for part in relative.parts)
            or relative.name in _PROTECTED_NAMES
        )

    @staticmethod
    def _has_symlink_ancestor(root: Path, candidate: Path) -> bool:
        cursor = candidate
        while cursor != root:
            if cursor.is_symlink():
                return True
            cursor = cursor.parent
        return False

    @classmethod
    def _project_files(cls, root: Path) -> list[tuple[str, bytes, str]]:
        records: list[tuple[str, bytes, str]] = []
        total = 0
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file() or cls._has_symlink_ancestor(root, candidate):
                continue
            relative = candidate.relative_to(root)
            if cls._is_protected(relative):
                continue
            resolved = candidate.resolve()
            resolved.relative_to(root)
            size = candidate.stat().st_size
            if size > MAX_GITHUB_FILE_BYTES:
                raise ValueError("%s excede o limite de 20 MB para sincronização." % relative.as_posix())
            total += size
            if total > MAX_GITHUB_PROJECT_BYTES:
                raise ValueError("O projeto excede o limite de 200 MB para sincronização.")
            mode = "100755" if candidate.stat().st_mode & 0o111 else "100644"
            records.append((relative.as_posix(), candidate.read_bytes(), mode))
            if len(records) > MAX_GITHUB_FILES:
                raise ValueError("O projeto excede o limite de 5.000 arquivos para sincronização.")
        if not records:
            raise ValueError("O projeto ainda não possui arquivos publicáveis.")
        return records

    @staticmethod
    def _git_blob_sha(content: bytes) -> str:
        return sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()

    @staticmethod
    def _create_blob(api: GitHubApi, owner: str, repo: str, content: bytes) -> str:
        result = api.request("POST", "/repos/%s/%s/git/blobs" % (quote(owner), quote(repo)), {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        })
        if not isinstance(result, dict) or not result.get("sha"):
            raise GitHubApiError(502, "O GitHub não confirmou o arquivo enviado.")
        return str(result["sha"])

    def sync(self, project_id: str, tenant_id: str, message: str = "Atualização pelo Olympus") -> SyncResult:
        binding = self._binding(project_id, tenant_id)
        api = self._api(tenant_id)
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        local_files = self._project_files(root)
        head = self._reference(api, binding.owner, binding.repo, binding.branch)
        commit = api.request("GET", "/repos/%s/%s/git/commits/%s" % (quote(binding.owner), quote(binding.repo), quote(head)))
        if not isinstance(commit, dict) or not isinstance(commit.get("tree"), dict) or not commit["tree"].get("sha"):
            raise GitHubApiError(502, "O GitHub não retornou a árvore atual.")
        base_tree = str(commit["tree"]["sha"])
        remote = api.request("GET", "/repos/%s/%s/git/trees/%s?recursive=1" % (quote(binding.owner), quote(binding.repo), quote(base_tree)))
        if not isinstance(remote, dict) or remote.get("truncated"):
            raise GitHubApiError(409, "A árvore remota é grande demais para sincronizar com segurança.")
        remote_shas = {
            str(item.get("path")): str(item.get("sha"))
            for item in remote.get("tree", [])
            if isinstance(item, dict) and item.get("type") == "blob" and item.get("path") and item.get("sha")
        }
        changes = []
        for path, content, mode in local_files:
            digest = self._git_blob_sha(content)
            if remote_shas.get(path) == digest:
                continue
            changes.append({"path": path, "mode": mode, "type": "blob", "sha": self._create_blob(api, binding.owner, binding.repo, content)})
        if not changes:
            return SyncResult(binding.owner, binding.repo, binding.branch, head, binding.html_url + "/commit/" + head, 0, True)
        tree = api.request("POST", "/repos/%s/%s/git/trees" % (quote(binding.owner), quote(binding.repo)), {
            "base_tree": base_tree,
            "tree": changes,
        })
        if not isinstance(tree, dict) or not tree.get("sha"):
            raise GitHubApiError(502, "O GitHub não confirmou a nova árvore.")
        created = api.request("POST", "/repos/%s/%s/git/commits" % (quote(binding.owner), quote(binding.repo)), {
            "message": self._commit_message(message),
            "tree": str(tree["sha"]),
            "parents": [head],
        })
        if not isinstance(created, dict) or not created.get("sha"):
            raise GitHubApiError(502, "O GitHub não confirmou o commit.")
        commit_sha = str(created["sha"])
        api.request("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (
            quote(binding.owner), quote(binding.repo), quote(binding.branch, safe="/"),
        ), {"sha": commit_sha, "force": False})
        updated = RepositoryBinding(**{**asdict(binding), "last_commit_sha": commit_sha, "updated_at": time.time()})
        self.bindings.put(updated)
        return SyncResult(
            binding.owner, binding.repo, binding.branch, commit_sha,
            str(created.get("html_url") or binding.html_url + "/commit/" + commit_sha), len(changes), False,
        )

    def auto_sync(self, project_id: str, tenant_id: str, message: str) -> Optional[SyncResult]:
        binding = self.bindings.get(project_id, tenant_id)
        if not binding or not binding.auto_sync or not self.account(tenant_id):
            return None
        return self.sync(project_id, tenant_id, message)

    @classmethod
    def _publish_files(cls, root: Path, repo: str) -> list[tuple[str, bytes, str]]:
        entrypoint = next((root / name for name in _STATIC_ENTRYPOINTS if (root / name).is_file() and not (root / name).is_symlink()), None)
        if entrypoint is None:
            raise ValueError("A publicação em um clique requer um projeto HTML estático ou um build em dist/build.")
        source_root = entrypoint.parent.resolve()
        source_root.relative_to(root)
        records = []
        total = 0
        for candidate in sorted(source_root.rglob("*")):
            if not candidate.is_file() or cls._has_symlink_ancestor(source_root, candidate):
                continue
            relative = candidate.relative_to(source_root)
            if cls._is_protected(relative) or candidate.suffix.lower() not in _PUBLISH_EXTENSIONS:
                continue
            resolved = candidate.resolve()
            resolved.relative_to(source_root)
            content = candidate.read_bytes()
            if len(content) > MAX_GITHUB_FILE_BYTES:
                raise ValueError("%s excede o limite de publicação." % relative.as_posix())
            total += len(content)
            if total > MAX_GITHUB_PROJECT_BYTES:
                raise ValueError("O site excede o limite de 200 MB para publicação.")
            if candidate.suffix.lower() in {".html", ".htm", ".css"}:
                try:
                    text = content.decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise ValueError("%s não está em UTF-8 e não pode ser publicado com segurança." % relative.as_posix()) from exc
                prefix = "/%s/" % repo
                if candidate.suffix.lower() in {".html", ".htm"}:
                    text = re.sub(
                        r"(?P<attr>\b(?:src|href|poster)\s*=\s*)(?P<quote>['\"])/(?!/)",
                        lambda match: match.group("attr") + match.group("quote") + prefix,
                        text,
                        flags=re.IGNORECASE,
                    )
                else:
                    text = re.sub(r"url\(\s*(['\"]?)/(?!/)", lambda match: "url(" + match.group(1) + prefix, text)
                content = text.encode("utf-8")
            records.append((relative.as_posix(), content, "100644"))
            if len(records) > MAX_GITHUB_FILES:
                raise ValueError("O site excede o limite de 5.000 arquivos para publicação.")
        if not any(path == "index.html" for path, _, _ in records):
            raise ValueError("A raiz publicável não contém index.html.")
        return records

    def publish(self, project_id: str, tenant_id: str) -> PublishResult:
        binding = self._binding(project_id, tenant_id)
        if binding.private:
            raise ValueError("Na v1.7, a publicação gratuita exige um repositório público.")
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        files = self._publish_files(root, binding.repo)
        self.sync(project_id, tenant_id, "Olympus: versão preparada para publicação")
        binding = self._binding(project_id, tenant_id)
        api = self._api(tenant_id)
        tree_entries = [
            {"path": path, "mode": mode, "type": "blob", "sha": self._create_blob(api, binding.owner, binding.repo, content)}
            for path, content, mode in files
        ]
        main_head = self._reference(api, binding.owner, binding.repo, binding.branch)
        try:
            pages_head = self._reference(api, binding.owner, binding.repo, PAGES_BRANCH)
            branch_exists = True
        except GitHubApiError as exc:
            if exc.status != 404:
                raise
            pages_head, branch_exists = main_head, False
        tree = api.request("POST", "/repos/%s/%s/git/trees" % (quote(binding.owner), quote(binding.repo)), {"tree": tree_entries})
        if not isinstance(tree, dict) or not tree.get("sha"):
            raise GitHubApiError(502, "O GitHub não confirmou os arquivos do site.")
        commit = api.request("POST", "/repos/%s/%s/git/commits" % (quote(binding.owner), quote(binding.repo)), {
            "message": "Publicação pelo Olympus",
            "tree": str(tree["sha"]),
            "parents": [pages_head],
        })
        if not isinstance(commit, dict) or not commit.get("sha"):
            raise GitHubApiError(502, "O GitHub não confirmou a publicação.")
        commit_sha = str(commit["sha"])
        if branch_exists:
            api.request("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (quote(binding.owner), quote(binding.repo), PAGES_BRANCH), {"sha": commit_sha, "force": False})
        else:
            api.request("POST", "/repos/%s/%s/git/refs" % (quote(binding.owner), quote(binding.repo)), {"ref": "refs/heads/" + PAGES_BRANCH, "sha": commit_sha})
        pages_path = "/repos/%s/%s/pages" % (quote(binding.owner), quote(binding.repo))
        try:
            pages = api.request("GET", pages_path)
            api.request("PUT", pages_path, {"build_type": "legacy", "source": {"branch": PAGES_BRANCH, "path": "/"}, "https_enforced": True})
        except GitHubApiError as exc:
            if exc.status != 404:
                raise
            pages = api.request("POST", pages_path, {"build_type": "legacy", "source": {"branch": PAGES_BRANCH, "path": "/"}})
        build = None
        try:
            build = api.request("POST", pages_path + "/builds")
        except GitHubApiError as exc:
            if exc.status not in {409, 422}:
                raise
        url = str((pages if isinstance(pages, dict) else {}).get("html_url") or "https://%s.github.io/%s/" % (binding.owner, binding.repo))
        status = str((build if isinstance(build, dict) else {}).get("status") or (pages if isinstance(pages, dict) else {}).get("status") or "queued")
        updated = RepositoryBinding(**{
            **asdict(binding), "pages_url": url, "pages_status": status,
            "last_commit_sha": binding.last_commit_sha, "updated_at": time.time(),
        })
        self.bindings.put(updated)
        return PublishResult(url, status, PAGES_BRANCH, commit_sha, len(files))

    def publication_status(self, project_id: str, tenant_id: str) -> Optional[dict]:
        binding = self._binding(project_id, tenant_id)
        if not binding.pages_url:
            return None
        api = self._api(tenant_id)
        pages_path = "/repos/%s/%s/pages" % (quote(binding.owner), quote(binding.repo))
        pages = api.request("GET", pages_path)
        latest = api.request("GET", pages_path + "/builds/latest")
        status = str((latest if isinstance(latest, dict) else {}).get("status") or (pages if isinstance(pages, dict) else {}).get("status") or "unknown")
        error = (latest.get("error") or {}).get("message") if isinstance(latest, dict) and isinstance(latest.get("error"), dict) else None
        updated = RepositoryBinding(**{
            **asdict(binding),
            "pages_url": str((pages if isinstance(pages, dict) else {}).get("html_url") or binding.pages_url),
            "pages_status": status,
            "updated_at": time.time(),
        })
        self.bindings.put(updated)
        return {"url": updated.pages_url, "status": status, "error": str(error)[:500] if error else None}

    def commits(self, project_id: str, tenant_id: str, limit: int = 20) -> list[dict]:
        binding = self._binding(project_id, tenant_id)
        api = self._api(tenant_id)
        data = api.request("GET", "/repos/%s/%s/commits?sha=%s&per_page=%s" % (
            quote(binding.owner), quote(binding.repo), quote(binding.branch, safe="/"), max(1, min(50, int(limit))),
        ))
        if not isinstance(data, list):
            raise GitHubApiError(502, "O GitHub não retornou o histórico de commits.")
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            detail = item.get("commit") if isinstance(item.get("commit"), dict) else {}
            author = detail.get("author") if isinstance(detail.get("author"), dict) else {}
            result.append({
                "sha": str(item.get("sha") or "")[:64],
                "message": str(detail.get("message") or "")[:500],
                "author": str(author.get("name") or "GitHub")[:200],
                "date": str(author.get("date") or "")[:100],
                "html_url": str(item.get("html_url") or "")[:1000],
            })
        return result
