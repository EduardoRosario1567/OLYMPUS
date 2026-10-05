from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional
import json
import filecmp
import re
import shutil
import time
import uuid
import zipfile

from .project_catalog import ProjectCatalogError, remove_project, rename_project


_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")
_RUNTIME_ROOTS = {".executions", ".git", ".next", ".olympus", "node_modules", "coverage"}


def _copy_ignore(_directory, names):
    return [name for name in names if name in _RUNTIME_ROOTS or name == ".env" or name.startswith(".env.")]


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    name: str
    root: str
    created_at: float
    updated_at: float
    tenant_id: str = "local"


class ProjectWorkspaceManager:
    """Persistent project/workspace boundary for cloud executions.

    Each project owns a persistent directory. Individual executions receive a
    child workspace copied from that project at submission time, preserving
    project isolation while keeping mission work durable across executions.
    """

    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.projects_root = self.data_dir / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.data_dir / "projects.json"
        self._lock = Lock()
        self._projects = self._load()

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = _SAFE_ID.sub("-", value.strip()).strip("-._")
        return (cleaned or "project")[:64]

    def _load(self) -> dict[str, dict]:
        if not self.index_path.is_file():
            return {}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._projects, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp.replace(self.index_path)

    def create(self, name: str, project_id: Optional[str] = None, tenant_id: str = "local") -> ProjectRecord:
        name = name.strip()
        if not name:
            raise ValueError("project name is required")
        with self._lock:
            pid = (project_id or (uuid.uuid4().hex[:12])).strip()
            if not pid:
                raise ValueError("project_id is required")
            if pid in self._projects:
                raise ValueError("project already exists")
            tenant_root = self.projects_root / self._slug(tenant_id)
            tenant_root.mkdir(parents=True, exist_ok=True)
            root = tenant_root / self._slug(pid)
            root.mkdir(parents=True, exist_ok=False)
            now = time.time()
            record = ProjectRecord(pid, name, str(root), now, now, tenant_id)
            self._projects[pid] = asdict(record)
            self._save()
            return record

    def get(self, project_id: str) -> Optional[ProjectRecord]:
        with self._lock:
            record = self._projects.get(project_id)
            return ProjectRecord(**record) if record else None

    def list(self, limit: int = 100, tenant_id: Optional[str] = None) -> list[ProjectRecord]:
        limit = max(1, int(limit))
        with self._lock:
            values = sorted(self._projects.values(), key=lambda item: item["created_at"])
            if tenant_id is not None:
                values = [item for item in values if item.get("tenant_id", "local") == tenant_id]
            return [ProjectRecord(**item) for item in values[:limit]]

    def rename(self, project_id: str, tenant_id: str, new_name: str) -> dict:
        with self._lock:
            current = self._projects.get(project_id)
            if current is None or current.get("tenant_id", "local") != tenant_id:
                raise ProjectCatalogError("Projeto não encontrado.")
            updated = rename_project(self.index_path, project_id, tenant_id, new_name)
            # Publish to readers only after the persistent write succeeds.
            self._projects[project_id] = updated
            return dict(updated)

    def remove(self, project_id: str, tenant_id: str) -> dict:
        with self._lock:
            current = self._projects.get(project_id)
            if current is None or current.get("tenant_id", "local") != tenant_id:
                raise ProjectCatalogError("Projeto não encontrado.")
            removed = remove_project(self.index_path, project_id, tenant_id)
            del self._projects[project_id]
            return removed

    def ensure(self, project_id: str, name: Optional[str] = None, tenant_id: str = "local") -> ProjectRecord:
        existing = self.get(project_id)
        if existing:
            if existing.tenant_id != tenant_id:
                raise PermissionError("project belongs to another tenant")
            return existing
        return self.create(name or project_id, project_id=project_id, tenant_id=tenant_id)

    def execution_workspace(self, project_id: str, execution_id: str, tenant_id: str = "local") -> Path:
        project = self.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            raise KeyError("project not found: %s" % project_id)
        workspace = Path(project.root) / ".executions" / execution_id
        is_new = not workspace.exists()
        workspace.mkdir(parents=True, exist_ok=True)
        if is_new:
            project_root = Path(project.root)
            for source in project_root.iterdir():
                if source.name in _RUNTIME_ROOTS or source.name == ".env" or source.name.startswith(".env."):
                    continue
                destination = workspace / source.name
                if source.is_dir():
                    shutil.copytree(source, destination, dirs_exist_ok=True, ignore=_copy_ignore)
                elif source.is_file():
                    shutil.copy2(source, destination)
        return workspace

    def promote_execution_files(
        self,
        project_id: str,
        execution_id: str,
        files: List[str],
        tenant_id: str = "local",
    ) -> tuple[str, ...]:
        project = self.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            raise KeyError("project not found: %s" % project_id)
        project_root = Path(project.root).resolve()
        workspace = (project_root / ".executions" / execution_id).resolve()
        if not workspace.is_dir():
            raise KeyError("execution workspace not found: %s" % execution_id)

        promoted = []
        with self._lock:
            for relative in dict.fromkeys(files):
                candidate = Path(str(relative).replace("\\", "/"))
                if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
                    raise ValueError("unsafe generated path: %s" % relative)
                if candidate.parts[0] == ".executions":
                    raise ValueError("reserved generated path: %s" % relative)
                source = (workspace / candidate).resolve()
                destination = (project_root / candidate).resolve()
                source.relative_to(workspace)
                destination.relative_to(project_root)
                if not source.is_file():
                    raise ValueError("generated file missing: %s" % relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                promoted.append(candidate.as_posix())
            if promoted:
                now = time.time()
                data = dict(self._projects[project_id])
                data["updated_at"] = now
                self._projects[project_id] = data
                self._save()
        return tuple(promoted)

    def discover_execution_changes(
        self,
        project_id: str,
        execution_id: str,
        tenant_id: str = "local",
    ) -> tuple[str, ...]:
        """Recover changed files from disk when a model report is incomplete.

        The execution workspace is authoritative for generated bytes. Comparing
        it with the persistent project prevents a lost in-memory report from
        producing a false successful mission with an empty preview.
        """
        project = self.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            raise KeyError("project not found: %s" % project_id)
        project_root = Path(project.root).resolve()
        workspace = (project_root / ".executions" / execution_id).resolve()
        if not workspace.is_dir():
            raise KeyError("execution workspace not found: %s" % execution_id)
        changed = []
        for source in sorted(workspace.rglob("*")):
            relative = source.relative_to(workspace)
            if (
                not source.is_file()
                or source.is_symlink()
                or any(part in _RUNTIME_ROOTS for part in relative.parts)
                or any(part == ".env" or part.startswith(".env.") for part in relative.parts)
            ):
                continue
            destination = project_root / relative
            if not destination.is_file() or not filecmp.cmp(source, destination, shallow=False):
                changed.append(relative.as_posix())
        return tuple(changed)

    def export_zip(self, project_id: str, tenant_id: str = "local") -> Path:
        project = self.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            raise KeyError("project not found: %s" % project_id)
        root = Path(project.root).resolve()
        export_root = self.data_dir / "exports" / self._slug(tenant_id)
        export_root.mkdir(parents=True, exist_ok=True)
        target = export_root / (self._slug(project.name) + ".zip")
        temporary = target.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(root.rglob("*")):
                relative = source.relative_to(root)
                if (
                    any(part in _RUNTIME_ROOTS for part in relative.parts)
                    or any(part == ".env" or part.startswith(".env.") for part in relative.parts)
                    or source.name == ".olympus-attachments.json"
                    or not source.is_file()
                ):
                    continue
                archive.write(source, relative.as_posix())
        temporary.replace(target)
        return target

    def project_root(self, project_id: str, tenant_id: str = "local") -> Path:
        project = self.get(project_id)
        if project is None or project.tenant_id != tenant_id:
            raise KeyError("project not found: %s" % project_id)
        return Path(project.root)
