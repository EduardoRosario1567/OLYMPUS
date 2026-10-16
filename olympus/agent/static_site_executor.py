"""Static-only model action boundary for an untrusted generated website.

This gate allows writing text assets, not running or importing model code.
It is NOT an OS sandbox and does NOT authorize browser rendering, publishing,
remote billing, or marking a mission DONE. The saved website still requires
the independent static-delivery validator and review.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from olympus.agent.actions import ActionType
from olympus.agent.executor import ActionExecutor, ActionObservation

_MAX_ACTION_BYTES = 512 * 1024
_ALLOWED_SUFFIXES = frozenset({".html", ".css", ".js", ".json", ".txt"})
_ALLOWED_ACTIONS = frozenset({
    ActionType.READ_FILE, ActionType.CREATE_FILE, ActionType.PATCH_FILE,
    ActionType.INSPECT_RESULT, ActionType.FINISH,
})
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class StaticSiteActionExecutor(ActionExecutor):
    """Write-only-to-site/ action executor; no process execution or I/O fetches."""

    def __init__(self, root: str):
        super().__init__(root, allowed_paths=("site/",))

    def _allowed_target(self, target: str) -> str:
        if not isinstance(target, str) or not target or "\\" in target:
            raise ValueError("BLOCKED: invalid static site path")
        p = PurePosixPath(target)
        parts = target.split("/")
        if (p.is_absolute() or len(parts) < 2 or len(parts) > 8
                or parts[0] != "site"
                or any(part in ("", ".", "..") or not _COMPONENT.fullmatch(part)
                       for part in parts)):
            raise ValueError("BLOCKED: only paths inside site/ are allowed")
        blocked_directories = {"node_modules", "vendor", "secrets", "credentials", "private", "backup", "backups"}
        sensitive_names = ("secret", "credential", "password", "token", "api_key", "apikey")
        if (p.suffix.lower() not in _ALLOWED_SUFFIXES
                or any(part.startswith(".") or part.lower() in blocked_directories
                       for part in parts)
                or any(word in p.name.lower() for word in sensitive_names)):
            raise ValueError("BLOCKED: unsupported static asset or private file")
        dest = self.root.joinpath(*parts)
        if not dest.resolve().is_relative_to(self.root):
            raise ValueError("BLOCKED: path escapes workspace")
        # A path can be lexically inside site yet point through an existing
        # symlink outside it. Do not delegate any symlinks to the file writer.
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("BLOCKED: symlink in static site path")
        return target

    def execute(self, action):
        try:
            if action.type not in _ALLOWED_ACTIONS:
                raise ValueError("BLOCKED: action not permitted in static site mode")
            if action.type in (ActionType.READ_FILE, ActionType.CREATE_FILE, ActionType.PATCH_FILE):
                self._allowed_target(action.target)
            if action.type == ActionType.CREATE_FILE:
                if not isinstance(action.payload, str):
                    raise ValueError("BLOCKED: static file content must be text")
                if len(action.payload.encode("utf-8")) > _MAX_ACTION_BYTES:
                    raise ValueError("BLOCKED: static asset exceeds size limit")
            if action.type == ActionType.PATCH_FILE:
                if not isinstance(action.payload, dict):
                    raise ValueError("BLOCKED: patch payload must be a mapping")
                content = action.payload.get("new_content")
                old_text = action.payload.get("old_text")
                if (not isinstance(content, str)
                        or len(content.encode("utf-8")) > _MAX_ACTION_BYTES
                        or (old_text is not None
                            and (not isinstance(old_text, str)
                                 or len(old_text.encode("utf-8")) > _MAX_ACTION_BYTES))):
                    raise ValueError("BLOCKED: static patch exceeds size limit")
                path = self.root / action.target
                if not path.is_file() or path.stat().st_size > _MAX_ACTION_BYTES:
                    raise ValueError("BLOCKED: target missing or exceeds size limit")
            if action.type == ActionType.READ_FILE:
                path = self.root / action.target
                if not path.is_file() or path.stat().st_size > _MAX_ACTION_BYTES:
                    raise ValueError("BLOCKED: requested file missing or too large")
        except (ValueError, OSError, UnicodeError) as exc:
            return ActionObservation(
                False, action, error=str(exc),
                metadata={"static_site_policy": "blocked"},
            )
        return super().execute(action)
