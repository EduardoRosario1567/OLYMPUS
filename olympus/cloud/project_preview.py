from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import Optional
import secrets
import time
import re

from .project_workspace import ProjectWorkspaceManager
from .project_studio import ProjectRuntimeManager


PREVIEW_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".mjs",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".mp4", ".webm",
}
ENTRYPOINTS = ("index.html", "app/index.html", "public/index.html", "dist/index.html", "build/index.html")
MAX_PREVIEW_FILE_BYTES = 10 * 1024 * 1024
BLOCKED_PREVIEW_ROOTS = {".executions", ".git", "attachments", "imports", "node_modules"}


@dataclass(frozen=True)
class PreviewSession:
    token: str
    project_id: str
    tenant_id: str
    entrypoint: str
    expires_at: float


class ProjectPreviewSessions:
    """Short-lived capability URLs for sandboxed static project previews."""

    def __init__(self, projects: ProjectWorkspaceManager, ttl_seconds: int = 600) -> None:
        self.projects = projects
        self.ttl_seconds = max(30, int(ttl_seconds))
        self._sessions: dict[str, PreviewSession] = {}
        self._lock = Lock()

    @staticmethod
    def _safe_relative(value: str) -> Path:
        relative = PurePosixPath((value or "").lstrip("/"))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
            or relative.parts[0] in BLOCKED_PREVIEW_ROOTS
            or any(part.startswith(".") for part in relative.parts)
        ):
            raise ValueError("unsafe preview path")
        path = Path(*relative.parts)
        if path.suffix.lower() not in PREVIEW_EXTENSIONS:
            raise ValueError("file type is not available in preview")
        return path

    def create(self, project_id: str, tenant_id: str = "local") -> PreviewSession:
        root = self.projects.project_root(project_id, tenant_id=tenant_id)
        entrypoint = None
        for name in ENTRYPOINTS:
            try:
                self._resolve_asset(root, name)
            except (KeyError, ValueError):
                continue
            entrypoint = name
            break
        if entrypoint is None:
            candidates = []
            for path in root.rglob("*.html"):
                relative = path.relative_to(root).as_posix()
                try:
                    self._resolve_asset(root, relative)
                except (KeyError, ValueError):
                    continue
                candidates.append(relative)
            candidates.sort()
            entrypoint = candidates[0] if candidates else None
        if entrypoint is None:
            raise ValueError("project has no HTML preview yet")
        now = time.time()
        session = PreviewSession(secrets.token_urlsafe(32), project_id, tenant_id, entrypoint, now + self.ttl_seconds)
        with self._lock:
            self._sessions = {token: item for token, item in self._sessions.items() if item.expires_at > now}
            self._sessions[session.token] = session
        return session

    def resolve(self, token: str, asset_path: Optional[str] = None) -> tuple[PreviewSession, Path]:
        with self._lock:
            session = self._sessions.get(token)
        if session is None or session.expires_at <= time.time():
            raise KeyError("preview session expired")
        root = self.projects.project_root(session.project_id, tenant_id=session.tenant_id)
        candidate = self._resolve_asset(root, asset_path or session.entrypoint)
        return session, candidate

    def _resolve_asset(self, root: Path, asset_path: str) -> Path:
        relative = self._safe_relative(asset_path)
        if root.is_symlink():
            raise ValueError("linked preview root is not allowed")
        root = root.resolve()
        candidate = root
        # Check each original component before resolve() erases link information.
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("links are not available in preview")
        try:
            resolved = candidate.resolve(strict=True)
            final_relative = resolved.relative_to(root)
            self._safe_relative(final_relative.as_posix())
            if not resolved.is_file() or resolved.stat().st_size > MAX_PREVIEW_FILE_BYTES:
                raise KeyError("preview file not found")
        except OSError as exc:
            raise KeyError("preview file not found") from exc
        return resolved

    @staticmethod
    def rewrite_text(token: str, extension: str, content: str) -> str:
        """Keep root-relative static assets inside the capability URL."""
        prefix = "/cloud/projects/_preview/%s" % token
        if extension in {".html", ".htm"}:
            rewritten = re.sub(
                r"(?P<attr>\b(?:src|href|poster)\s*=\s*)(?P<quote>['\"])/(?!/)",
                lambda match: match.group("attr") + match.group("quote") + prefix + "/",
                content,
                flags=re.IGNORECASE,
            )
            script = ProjectRuntimeManager.inspector_script()
            if re.search(r"</body\s*>", rewritten, re.IGNORECASE):
                return re.sub(r"</body\s*>", script + "</body>", rewritten, count=1, flags=re.IGNORECASE)
            return rewritten + script
        if extension == ".css":
            return re.sub(r"url\(\s*(['\"]?)/(?!/)", lambda match: "url(" + match.group(1) + prefix + "/", content)
        return content
