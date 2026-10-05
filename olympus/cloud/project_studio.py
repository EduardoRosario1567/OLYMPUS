from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from threading import RLock, Thread
from typing import Optional, Union
import http.client
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
try:
    import resource
except ImportError:  # pragma: no cover - Windows has no resource module
    resource = None

from .project_versions import ProjectVersion, ProjectVersionStore
from .project_workspace import ProjectWorkspaceManager


MAX_EDITOR_FILE_BYTES = 1024 * 1024
MAX_STUDIO_FILES = 2000
MAX_RUNTIME_LOG_LINES = 1000
MAX_ACTIVE_RUNTIMES = 2
RUNTIME_TTL_SECONDS = 30 * 60
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


class ProjectRuntimeManager:
    """Bounded local web runtimes for previews; never installs dependencies."""

    def __init__(self, projects: ProjectWorkspaceManager, ttl_seconds: int = RUNTIME_TTL_SECONDS, max_active: int = MAX_ACTIVE_RUNTIMES) -> None:
        self.projects = projects
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_active = max(1, int(max_active))
        self._sessions: dict[str, RuntimeSession] = {}
        self._project_tokens: dict[tuple[str, str], str] = {}
        self._logs: dict[str, deque[RuntimeLog]] = {}
        self._seq: dict[str, int] = {}
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
            "kind": "runtime", "framework": framework, "ready": ready,
            "message": "Pronto para executar" if ready else "Dependências do projeto ainda não estão disponíveis.",
            "package_root": str(package_path.parent), "script": script_name,
        }

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _safe_environment(port: int) -> dict[str, str]:
        allowed = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
        allowed.update({"NODE_ENV": "development", "NO_COLOR": "1", "HOST": "127.0.0.1", "PORT": str(port)})
        return allowed

    @staticmethod
    def _command(framework: str, package_root: str, port: int) -> list[str]:
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node.js não está disponível neste computador.")
        modules = Path(package_root) / "node_modules"
        if framework == "Next.js":
            return [node, str(modules / "next" / "dist" / "bin" / "next"), "dev", "--hostname", "127.0.0.1", "--port", str(port)]
        if framework == "Vite":
            return [node, str(modules / "vite" / "bin" / "vite.js"), "--host", "127.0.0.1", "--port", str(port), "--strictPort"]
        return [node, str(modules / "react-scripts" / "scripts" / "start.js")]

    @staticmethod
    def _runtime_limits():
        """Apply host-level damage limits for the local trusted preview.

        This is not a security sandbox. Production must run previews in a
        container/VM with a separate user, filesystem and network policy.
        """
        if resource is None:
            return None

        def limit_process():
            cpu_seconds = max(10, int(os.environ.get("OLYMPUS_PREVIEW_CPU_SECONDS", "120")))
            memory_bytes = max(512, int(os.environ.get("OLYMPUS_PREVIEW_MEMORY_MB", "2048"))) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

        return limit_process

    def _append_log(self, token: str, stream: str, message: str) -> None:
        clean = ANSI_ESCAPE.sub("", message).replace("\x00", "").rstrip()
        clean = SECRET_LINE.sub(lambda match: "%s=[protegido]" % match.group(1), clean)
        if not clean:
            return
        with self._lock:
            seq = self._seq.get(token, 0) + 1
            self._seq[token] = seq
            self._logs.setdefault(token, deque(maxlen=MAX_RUNTIME_LOG_LINES)).append(
                RuntimeLog(seq, time.time(), stream, clean[:4000])
            )

    def _read_output(self, token: str, process: subprocess.Popen) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                self._append_log(token, "runtime", line)
        finally:
            stream.close()
            code = process.poll()
            with self._lock:
                session = self._sessions.get(token)
                if session and session.process is process and code is not None:
                    session.status = "stopped" if code == 0 else "failed"
                    if code != 0 and not session.error:
                        session.error = "O preview executável foi encerrado com erro."

    @staticmethod
    def _listening(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            return False

    def start(self, project_id: str, tenant_id: str = "local") -> RuntimeSession:
        production = os.environ.get("OLYMPUS_ENV", "development").strip().lower() in {"production", "prod"}
        if production and os.environ.get("OLYMPUS_ALLOW_UNSANDBOXED_PREVIEW", "").lower() not in {"1", "true", "yes"}:
            raise RuntimeError("Preview executável exige sandbox de container em produção.")
        info = self.detect(project_id, tenant_id)
        if info["kind"] != "runtime":
            raise ValueError(info["message"])
        if not info["ready"]:
            raise RuntimeError(info["message"])
        key = (tenant_id, project_id)
        with self._lock:
            existing_token = self._project_tokens.get(key)
            existing = self._sessions.get(existing_token or "")
            if existing and existing.process and existing.process.poll() is None:
                existing.expires_at = time.time() + self.ttl_seconds
                return existing
            if existing_token:
                self._sessions.pop(existing_token, None)
                self._logs.pop(existing_token, None)
                self._seq.pop(existing_token, None)
                self._project_tokens.pop(key, None)
            active = sum(1 for item in self._sessions.values() if item.process and item.process.poll() is None)
            if active >= self.max_active:
                raise RuntimeError("O limite de previews executáveis simultâneos foi atingido.")
        port = self._free_port()
        token = secrets.token_urlsafe(32)
        command = self._command(info["framework"], info["package_root"], port)
        process = subprocess.Popen(
            command,
            cwd=info["package_root"],
            env=self._safe_environment(port),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
            preexec_fn=self._runtime_limits(),
        )
        now = time.time()
        session = RuntimeSession(token, project_id, tenant_id, info["framework"], info["package_root"], port, "starting", now, now + self.ttl_seconds, process)
        with self._lock:
            self._sessions[token] = session
            self._project_tokens[key] = token
            self._logs[token] = deque(maxlen=MAX_RUNTIME_LOG_LINES)
            self._seq[token] = 0
        Thread(target=self._read_output, args=(token, process), daemon=True).start()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            if self._listening(port):
                session.status = "running"
                self._append_log(token, "olympus", "%s iniciado com segurança." % session.framework)
                return session
            time.sleep(0.1)
        session.status = "failed"
        session.error = "O projeto não iniciou dentro do tempo esperado."
        self.stop(project_id, tenant_id)
        raise RuntimeError(session.error)

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
                if session.process and session.process.poll() is not None and session.status in {"starting", "running"}:
                    session.status = "stopped" if session.process.returncode == 0 else "failed"
            result = session
        if expired:
            self.stop(project_id, tenant_id)
            return None
        return result

    def stop(self, project_id: str, tenant_id: str = "local") -> bool:
        key = (tenant_id, project_id)
        with self._lock:
            token = self._project_tokens.pop(key, None)
            session = self._sessions.pop(token or "", None)
            if token:
                self._logs.pop(token, None)
                self._seq.pop(token, None)
        if not session:
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
        if token:
            with self._lock:
                self._logs.pop(token, None)
                self._seq.pop(token, None)
        return True

    def close(self) -> None:
        with self._lock:
            projects = [(tenant_id, project_id) for tenant_id, project_id in self._project_tokens]
        for tenant_id, project_id in projects:
            self.stop(project_id, tenant_id)

    def logs(self, project_id: str, tenant_id: str = "local", after: int = 0) -> list[RuntimeLog]:
        session = self.get(project_id, tenant_id)
        if not session:
            return []
        with self._lock:
            return [item for item in self._logs.get(session.token, ()) if item.seq > max(0, int(after))]

    def resolve(self, token: str) -> RuntimeSession:
        with self._lock:
            session = self._sessions.get(token)
        if not session or session.expires_at <= time.time() or session.status != "running" or not session.process or session.process.poll() is not None:
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
        session = self.resolve(token)
        relative = PurePosixPath((asset_path or "").lstrip("/"))
        safe_path = "/" + (asset_path or "").lstrip("/")
        if "\x00" in safe_path or ".." in relative.parts or len(safe_path) > 4096 or len(query) > 4096:
            raise ValueError("unsafe runtime path")
        connection = http.client.HTTPConnection("127.0.0.1", session.port, timeout=10)
        try:
            target = safe_path + (("?" + query) if query else "")
            connection.request("GET", target, headers={"Accept": "*/*", "User-Agent": "OLYMPUS-Preview/1.6"})
            response = connection.getresponse()
            body = response.read(MAX_EDITOR_FILE_BYTES * 20 + 1)
            if len(body) > MAX_EDITOR_FILE_BYTES * 20:
                raise ValueError("runtime response too large")
            content_type = response.getheader("Content-Type") or mimetypes.guess_type(asset_path)[0] or "application/octet-stream"
            if any(kind in content_type for kind in ("text/html", "text/css", "javascript")):
                body = self.rewrite_text(token, content_type, body)
            headers = {"Content-Type": content_type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
            location = response.getheader("Location")
            if location and location.startswith("/") and not location.startswith("//"):
                headers["Location"] = "/cloud/projects/_runtime/%s%s" % (token, location)
            elif location and location.startswith("http://127.0.0.1:%s/" % session.port):
                headers["Location"] = "/cloud/projects/_runtime/%s/%s" % (token, location.split("/", 3)[-1])
            return response.status, headers, body
        finally:
            connection.close()
