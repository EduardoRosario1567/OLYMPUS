from __future__ import annotations

from collections import deque, Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from threading import RLock, Event, Thread
from typing import Optional, Union
import json
import mimetypes
import os
import re
import secrets
import subprocess
import tempfile
import time

from .project_versions import ProjectVersion, ProjectVersionStore
from .project_workspace import ProjectWorkspaceManager
from .preview_container import PreviewContainer, PreviewContainerExecutor, PreviewLifecycleError


MAX_EDITOR_FILE_BYTES = 1024 * 1024
MAX_STUDIO_FILES = 2000
MAX_RUNTIME_LOG_LINES = 1000
MAX_ACTIVE_RUNTIMES = 2
RUNTIME_TTL_SECONDS = 30 * 60
PREVIEW_ISOLATION_MESSAGE = "Preview executável indisponível: o executor isolado ainda não foi homologado."
BLOCKED_ROOTS = {
    ".executions", ".git", ".next", ".olympus", "attachments", "imports",
    "node_modules", "dist", "build", "coverage",
}
BLOCKED_NAMES = {
    ".olympus-attachments.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
}
TEXT_EXTENSIONS = {
    ".css", ".graphql", ".htm", ".html", ".ini", ".java", ".js", ".jsx",
    ".json", ".md", ".mjs", ".py", ".rb", ".rs", ".scss", ".sh", ".sql",
    ".svg", ".toml", ".ts", ".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile"}
ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SECRET_LINE = re.compile(r"(?i)\b(api[_-]?key|authorization|password|passwd|secret|token)\b\s*[:=]\s*([^\r\n]+)")
SAFE_SCRIPT = re.compile(r"^(?:next(?:\s+(?:dev|start))?|vite|react-scripts\s+start)(?:\s+[A-Za-z0-9._/@:=+-]+)*$")


@dataclass(frozen=True)
class StudioFile:
    path: str
    size: int
    sha256: str
    updated_at: float


@dataclass(frozen=True)
class RuntimeLog:
    seq: int
    at: float
    stream: str
    message: str


@dataclass
class RuntimeSession:
    token: str
    project_id: str
    tenant_id: str
    framework: str
    project_path: str
    port: int
    status: str
    started_at: float
    expires_at: float
    process: Optional[subprocess.Popen] = None
    error: Optional[str] = None
    container: Optional[PreviewContainer] = None


class ProjectFileEditor:
    """Tenant-scoped text editor with optimistic locking and safety snapshots."""

    def __init__(self, projects: ProjectWorkspaceManager, versions: ProjectVersionStore) -> None:
        self.projects = projects
        self.versions = versions
        self._lock = RLock()

    @staticmethod
    def _safe_relative(value: str) -> Path:
        raw = PurePosixPath((value or "").replace("\\", "/"))
        if raw.is_absolute() or not raw.parts or ".." in raw.parts:
            raise ValueError("unsafe file path")
        path = Path(*raw.parts)
        if (
            path.parts[0] in BLOCKED_ROOTS
            or any(part.startswith(".") for part in path.parts)
            or path.name in BLOCKED_NAMES
            or (path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in TEXT_NAMES)
        ):
            raise ValueError("file is not available in the editor")
        return path

    @staticmethod
    def _digest_bytes(content: bytes) -> str:
        return sha256(content).hexdigest()

    def _resolve(self, project_id: str, value: str, tenant_id: str) -> tuple[Path, Path]:
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        relative = self._safe_relative(value)
        unresolved = root / relative
        cursor = unresolved
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError("symbolic links are not editable")
            cursor = cursor.parent
        candidate = unresolved.resolve()
        candidate.relative_to(root)
        return root, candidate

    def list(self, project_id: str, tenant_id: str = "local") -> list[StudioFile]:
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        records: list[StudioFile] = []
        for candidate in sorted(root.rglob("*")):
            if len(records) >= MAX_STUDIO_FILES:
                break
            if not candidate.is_file() or candidate.is_symlink():
                continue
            relative = candidate.relative_to(root)
            try:
                self._safe_relative(relative.as_posix())
            except ValueError:
                continue
            size = candidate.stat().st_size
            if size > MAX_EDITOR_FILE_BYTES:
                continue
            content = candidate.read_bytes()
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            records.append(StudioFile(relative.as_posix(), size, self._digest_bytes(content), candidate.stat().st_mtime))
        return records

    def read(self, project_id: str, path: str, tenant_id: str = "local") -> tuple[StudioFile, str]:
        root, candidate = self._resolve(project_id, path, tenant_id)
        if not candidate.is_file() or candidate.stat().st_size > MAX_EDITOR_FILE_BYTES:
            raise KeyError("file not found")
        content = candidate.read_bytes()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("file is not UTF-8 text") from exc
        stat = candidate.stat()
        return StudioFile(candidate.relative_to(root).as_posix(), len(content), self._digest_bytes(content), stat.st_mtime), text

    def save(
        self,
        project_id: str,
        path: str,
        content: str,
        expected_sha256: str,
        tenant_id: str = "local",
    ) -> tuple[StudioFile, ProjectVersion]:
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("file exceeds the 1 MB editor limit")
        with self._lock:
            root, candidate = self._resolve(project_id, path, tenant_id)
            if not candidate.is_file():
                raise KeyError("file not found")
            current = candidate.read_bytes()
            if self._digest_bytes(current) != expected_sha256:
                raise RuntimeError("file changed since it was opened")
            if current == encoded:
                record, _ = self.read(project_id, path, tenant_id)
                snapshot = self.versions.capture(project_id, label="Editor sem alterações", reason="editor", tenant_id=tenant_id)
                return record, snapshot
            snapshot = self.versions.capture(
                project_id,
                label="Backup antes da edição de %s" % candidate.name,
                reason="pre_edit",
                tenant_id=tenant_id,
            )
            descriptor, temporary_name = tempfile.mkstemp(prefix=".olympus-edit-", dir=str(candidate.parent))
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as target:
                    target.write(encoded)
                    target.flush()
                    os.fsync(target.fileno())
                os.chmod(temporary, candidate.stat().st_mode)
                os.replace(temporary, candidate)
            finally:
                if temporary.exists():
                    temporary.unlink()
            record, _ = self.read(project_id, candidate.relative_to(root).as_posix(), tenant_id)
            return record, snapshot


class PreviewStopError(RuntimeError):
    pass


class ProjectRuntimeManager:
    """Owned container previews; no host execution or dependency installation."""

    def __init__(self, projects: ProjectWorkspaceManager, ttl_seconds: int = RUNTIME_TTL_SECONDS, max_active: int = MAX_ACTIVE_RUNTIMES, executor=None, startup_timeout_seconds: float = 20) -> None:
        self.projects = projects
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_active = max(1, int(max_active))
        self.executor = executor if executor is not None else PreviewContainerExecutor()
        if not 0 < startup_timeout_seconds <= 30:
            raise ValueError("Invalid preview startup timeout")
        self.startup_timeout_seconds = startup_timeout_seconds
        self._reaper_stop = Event()
        self._reaper = None
        self._sessions: dict[str, RuntimeSession] = {}
        self._project_tokens: dict[tuple[str, str], str] = {}
        self._logs: dict[str, deque[RuntimeLog]] = {}
        self._seq: dict[str, int] = {}
        self._process_log_cursor = {}
        self._log_unavailable = set()
        self._lock = RLock()

    @staticmethod
    def _package_candidates(root: Path) -> list[Path]:
        return [root / "package.json", root / "app" / "package.json", root / "frontend" / "package.json"]

    def detect(self, project_id: str, tenant_id: str = "local") -> dict:
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        package_path = None
        for path in self._package_candidates(root):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                path.resolve().relative_to(root)
                cursor = path.parent
                while cursor != root:
                    if cursor.is_symlink():
                        raise ValueError("package path contains a symbolic link")
                    cursor = cursor.parent
                package_path = path
                break
            except ValueError:
                continue
        if package_path is None:
            return {"kind": "static", "framework": "html", "ready": False, "message": "Projeto estático"}
        if package_path.stat().st_size > 256 * 1024:
            raise ValueError("package.json is too large")
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("package.json is invalid") from exc
        scripts = package.get("scripts") if isinstance(package, dict) else None
        deps = {}
        if isinstance(package, dict):
            for key in ("dependencies", "devDependencies"):
                if isinstance(package.get(key), dict):
                    deps.update(package[key])
        scripts = scripts if isinstance(scripts, dict) else {}
        script_name = "dev" if isinstance(scripts.get("dev"), str) else "start" if isinstance(scripts.get("start"), str) else None
        script = scripts.get(script_name) if script_name else None
        framework = None
        executable = None
        if "next" in deps or (isinstance(script, str) and script.startswith("next")):
            framework, executable = "Next.js", "next"
        elif "vite" in deps or (isinstance(script, str) and script.startswith("vite")):
            framework, executable = "Vite", "vite"
        elif "react-scripts" in deps or script == "react-scripts start":
            framework, executable = "React", "react-scripts"
        if not framework or not script_name or not isinstance(script, str) or not SAFE_SCRIPT.fullmatch(script.strip()):
            return {"kind": "unsupported", "framework": "desconhecido", "ready": False, "message": "Runtime web não reconhecido com segurança."}
        modules = package_path.parent / "node_modules"
        entrypoints = {
            "next": modules / "next" / "dist" / "bin" / "next",
            "vite": modules / "vite" / "bin" / "vite.js",
            "react-scripts": modules / "react-scripts" / "scripts" / "start.js",
        }
        binary = entrypoints[executable]
        ready = False
        if modules.is_dir() and not modules.is_symlink() and binary.exists():
            try:
                modules.resolve().relative_to(package_path.parent.resolve())
                binary.resolve().relative_to(modules.resolve())
                ready = True
            except ValueError:
                ready = False
        return {
            "kind": "runtime", "framework": framework, "ready": False,
            "dependencies_ready": ready, "isolation_status": "unavailable",
            "message": PREVIEW_ISOLATION_MESSAGE if ready else "Dependências do projeto ainda não estão disponíveis. " + PREVIEW_ISOLATION_MESSAGE,
            "package_root": str(package_path.parent), "script": script_name,
        }

    def _append_log(self, token: str, stream: str, message: str) -> None:
        clean = ANSI_ESCAPE.sub("", message)
        clean = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', clean).rstrip()
        clean = SECRET_LINE.sub(lambda match: "%s=[protegido]" % match.group(1), clean)
        if not clean:
            return
        with self._lock:
            seq = self._seq.get(token, 0) + 1
            self._seq[token] = seq
            self._logs.setdefault(token, deque(maxlen=MAX_RUNTIME_LOG_LINES)).append(
                RuntimeLog(seq, time.time(), stream, clean[:4000])
            )

    def _expire_sessions(self):
        with self._lock:
            expired = [(session.project_id, session.tenant_id) for session in self._sessions.values()
                if session.expires_at <= time.time()]
            for project_id, tenant_id in expired:
                self.stop(project_id, tenant_id)

    def _start_reaper(self):
        if self._reaper is not None:
            return
        def reap():
            while not self._reaper_stop.wait(5):
                self._expire_sessions()
        self._reaper = Thread(target=reap, daemon=True)
        self._reaper.start()

    def start(self, project_id: str, tenant_id: str = "local") -> RuntimeSession:
        info = self.detect(project_id, tenant_id)
        if info["kind"] != "runtime":
            raise ValueError(info["message"])
        root = self.projects.project_root(project_id, tenant_id=tenant_id)
        relative = Path(info["package_root"]).relative_to(root.resolve()).as_posix()
        key = (tenant_id, project_id)
        with self._lock:
            if self._reaper_stop.is_set():
                raise RuntimeError("Gerenciador de previews encerrado.")
            self._expire_sessions()
            existing = self.get(project_id, tenant_id)
            if existing and existing.status == "running":
                existing.expires_at = time.time() + self.ttl_seconds
                return existing
            if key in self._project_tokens and not self.stop(project_id, tenant_id):
                raise RuntimeError("A remoção do preview anterior ainda não foi confirmada.")
            for handle in self.executor.pending():
                if not self.executor.stop(handle):
                    raise RuntimeError("Há um container de preview com remoção não confirmada.")
            if len(self._sessions) >= self.max_active:
                raise RuntimeError("O limite de previews executáveis simultâneos foi atingido.")
            try:
                handle = self.executor.start(root, info["framework"], relative)
            except PreviewLifecycleError as exc:
                raise RuntimeError(PREVIEW_ISOLATION_MESSAGE) from exc
            now = time.time()
            token = secrets.token_urlsafe(32)
            session = RuntimeSession(token, project_id, tenant_id, info["framework"],
                info["package_root"], 0, "starting", now, now + self.ttl_seconds, container=handle)
            self._sessions[token] = session
            self._project_tokens[key] = token
            self._logs[token] = deque(maxlen=MAX_RUNTIME_LOG_LINES)
            self._seq[token] = 0
            self._start_reaper()
            try:
                deadline = time.monotonic() + self.startup_timeout_seconds
                while time.monotonic() < deadline:
                    try:
                        status, headers, _ = self.executor.fetch(handle)
                        if 200 <= status < 300 and "text/html" in headers.get("Content-Type", "").lower():
                            session.status = "running"
                            self._append_log(token, "olympus", "Preview isolado confirmou resposta HTTP.")
                            return session
                    except PreviewLifecycleError:
                        pass
                    time.sleep(min(0.2, max(0, deadline - time.monotonic())))
                raise RuntimeError("O preview isolado não confirmou uma página HTTP dentro do prazo.")
            except BaseException:
                self.stop(project_id, tenant_id)
                raise

    def get(self, project_id: str, tenant_id: str = "local") -> Optional[RuntimeSession]:
        with self._lock:
            token = self._project_tokens.get((tenant_id, project_id))
            session = self._sessions.get(token or "")
            if not session:
                return None
            if session.expires_at <= time.time():
                expired = True
            else:
                expired = False
                if session.container and session.status == "running" and not self.executor.running(session.container):
                    session.status = "failed"
                    session.error = "O container do preview não está disponível."
                if session.process and session.process.poll() is not None and session.status in {"starting", "running"}:
                    session.status = "stopped" if session.process.returncode == 0 else "failed"
            result = session
        if expired:
            if self.stop(project_id, tenant_id):
                return None
            return session
        return result

    def stop(self, project_id: str, tenant_id: str = "local") -> bool:
        key = (tenant_id, project_id)
        with self._lock:
            token = self._project_tokens.get(key)
            session = self._sessions.get(token or "")
            if not session:
                return False
            if session.container and not self.executor.stop(session.container):
                session.status = "cleanup_unconfirmed"
                session.error = "A remoção do container ainda não foi confirmada."
                session.expires_at = time.time()
                return False
            process = session.process
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            session.status = "stopped"
            session.expires_at = time.time()
            self._project_tokens.pop(key, None)
            self._sessions.pop(token, None)
            self._logs.pop(token, None)
            self._seq.pop(token, None)
            self._process_log_cursor.pop(token, None)
            self._log_unavailable.discard(token)
            return True

    def stop_checked(self, project_id: str, tenant_id: str = "local") -> bool:
        with self._lock:
            if (tenant_id, project_id) not in self._project_tokens:
                return False
            if not self.stop(project_id, tenant_id):
                raise PreviewStopError("A remoção do container de preview ainda não foi confirmada.")
            return True

    def close(self) -> None:
        self._reaper_stop.set()
        with self._lock:
            projects = [(tenant_id, project_id) for tenant_id, project_id in self._project_tokens]
        for tenant_id, project_id in projects:
            self.stop(project_id, tenant_id)
        for handle in self.executor.pending():
            self.executor.stop(handle)
        if self._reaper is not None:
            self._reaper.join(timeout=2)
        self.executor.close()

    def logs(self, project_id: str, tenant_id: str = "local", after: int = 0) -> list[RuntimeLog]:
        # Ownership must be checked even for a missing session, before Docker.
        self.projects.project_root(project_id, tenant_id=tenant_id)
        session = self.get(project_id, tenant_id)
        if not session:
            return []
        with self._lock:
            if self._sessions.get(session.token) is not session:
                return []
            if session.container and session.status in {'starting', 'running', 'failed'}:
                try:
                    entries = self.executor.logs(session.container)
                    timestamp, previous = self._process_log_cursor.get(session.token, ('', Counter()))
                    counts = Counter()
                    newest = timestamp
                    newest_counts = previous.copy()
                    for at, stream, message in entries:
                        if at < timestamp:
                            continue
                        key = (stream, message)
                        counts[(at, key)] += 1
                        if at > timestamp or counts[(at, key)] > previous[key]:
                            self._append_log(session.token, stream, message)
                        if at > newest:
                            newest = at
                            newest_counts = Counter()
                        if at == newest:
                            newest_counts[key] = max(newest_counts[key], counts[(at, key)])
                    self._process_log_cursor[session.token] = (newest, newest_counts)
                    self._log_unavailable.discard(session.token)
                except PreviewLifecycleError:
                    if session.token not in self._log_unavailable:
                        self._append_log(session.token, 'olympus', 'Não foi possível consultar a saída do container nesta leitura.')
                        self._log_unavailable.add(session.token)
            return [item for item in self._logs.get(session.token, ()) if item.seq > max(0, int(after))]

    def resolve(self, token: str) -> RuntimeSession:
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                raise KeyError("runtime session unavailable")
            if session.expires_at <= time.time():
                self.stop(session.project_id, session.tenant_id)
                raise KeyError("runtime session unavailable")
            if session.status != "running" or not session.container or not self.executor.running(session.container):
                raise KeyError("runtime session unavailable")
            session.expires_at = time.time() + self.ttl_seconds
            return session

    @staticmethod
    def inspector_script() -> str:
        return """<script>(function(){let on=false,last=null;function sel(e){if(e.id)return'#'+CSS.escape(e.id);let p=[];while(e&&e.nodeType===1&&p.length<5){let s=e.tagName.toLowerCase();if(e.classList.length)s+='.'+Array.from(e.classList).slice(0,2).map(CSS.escape).join('.');p.unshift(s);e=e.parentElement}return p.join(' > ')}window.addEventListener('message',e=>{if(e.data&&e.data.type==='olympus-inspect-mode'){on=!!e.data.enabled;document.documentElement.style.cursor=on?'crosshair':'';if(!on&&last){last.style.outline='';last=null}}});document.addEventListener('mouseover',e=>{if(!on)return;if(last)last.style.outline='';last=e.target;last.style.outline='2px solid #22d3ee';last.style.outlineOffset='2px'},true);document.addEventListener('click',e=>{if(!on)return;e.preventDefault();e.stopPropagation();let t=e.target;parent.postMessage({type:'olympus-element-selected',selector:sel(t),tag:t.tagName.toLowerCase(),text:(t.innerText||t.getAttribute('aria-label')||'').trim().slice(0,160)},'*')},true)})();</script>"""

    @classmethod
    def rewrite_text(cls, token: str, content_type: str, content: bytes) -> bytes:
        prefix = "/cloud/projects/_runtime/%s" % token
        text = content.decode("utf-8", errors="replace")
        if "text/html" in content_type:
            text = re.sub(
                r"(?P<attr>\b(?:src|href|action|poster)\s*=\s*)(?P<quote>['\"])/(?!/)",
                lambda match: match.group("attr") + match.group("quote") + prefix + "/",
                text,
                flags=re.IGNORECASE,
            )
            script = cls.inspector_script()
            text = re.sub(r"</body\s*>", script + "</body>", text, count=1, flags=re.IGNORECASE) if re.search(r"</body\s*>", text, re.IGNORECASE) else text + script
        elif "text/css" in content_type:
            text = re.sub(r"url\(\s*(['\"]?)/(?!/)", lambda match: "url(" + match.group(1) + prefix + "/", text)
        elif "javascript" in content_type:
            text = text.replace('"/_next/', '"' + prefix + '/_next/').replace("'/_next/", "'" + prefix + "/_next/")
        return text.encode("utf-8")

    def proxy(self, token: str, asset_path: str = "", query: str = "") -> tuple[int, dict[str, str], bytes]:
        safe_path = "/" + (asset_path or "").lstrip("/")
        self.executor._request_path(safe_path, query)
        session = self.resolve(token)
        status, upstream_headers, body = self.executor.fetch(session.container, safe_path, query)
        content_type = upstream_headers.get("Content-Type", "application/octet-stream")
        if any(kind in content_type.lower() for kind in ("text/html", "text/css", "javascript")):
            body = self.rewrite_text(token, content_type.lower(), body)
        headers = {"Content-Type": content_type, "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Access-Control-Allow-Origin": "*",
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"}
        location = upstream_headers.get("Location")
        prefix = "/cloud/projects/_runtime/%s" % token
        if location and location.startswith("/") and not location.startswith("//"):
            headers["Location"] = prefix + location
        elif location and location.startswith("http://127.0.0.1:3000/"):
            headers["Location"] = prefix + "/" + location.split("/", 3)[-1]
        return status, headers, body
