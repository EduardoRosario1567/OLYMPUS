from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Optional, Union
import json
import shutil
import time
import uuid

from .project_workspace import ProjectWorkspaceManager


_PROTECTED_ROOTS = {".executions", ".git", ".next", "attachments", "imports", "node_modules", "coverage"}
_PROTECTED_FILES = {".olympus-attachments.json"}
MAX_VERSION_FILES = 5000
MAX_VERSION_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class ProjectVersion:
    version_id: str
    project_id: str
    label: str
    reason: str
    created_at: float
    file_count: int
    size_bytes: int
    execution_id: Optional[str] = None


class ProjectVersionStore:
    """Immutable project snapshots with verified, rollback-safe restoration."""

    def __init__(self, projects: ProjectWorkspaceManager, storage_root: Union[str, Path]) -> None:
        self.projects = projects
        self.storage_root = Path(storage_root).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @staticmethod
    def _is_protected(relative: Path) -> bool:
        if not relative.parts:
            return True
        first = relative.parts[0]
        return (
            first in _PROTECTED_ROOTS
            or first in _PROTECTED_FILES
            or any(part == ".env" or part.startswith(".env.") for part in relative.parts)
        )

    @staticmethod
    def _digest(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _assert_no_symlinks(root: Path) -> None:
        for path in root.rglob("*"):
            if path.is_symlink() and not ProjectVersionStore._is_protected(path.relative_to(root)):
                raise ValueError("project contains symbolic links that cannot be versioned safely")

    @staticmethod
    def _clean_label(value: Optional[str], fallback: str) -> str:
        label = " ".join((value or fallback).strip().split())
        return label[:100] or fallback

    def _bucket(self, project_id: str, tenant_id: str) -> Path:
        key = sha256((tenant_id + "\0" + project_id).encode("utf-8")).hexdigest()[:24]
        bucket = self.storage_root / key
        bucket.mkdir(parents=True, exist_ok=True)
        return bucket

    @staticmethod
    def _index_path(bucket: Path) -> Path:
        return bucket / "versions.json"

    def _load_index(self, bucket: Path) -> dict[str, dict]:
        path = self._index_path(bucket)
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_index(self, bucket: Path, records: dict[str, dict]) -> None:
        target = self._index_path(bucket)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(target)

    @staticmethod
    def _record(value: dict) -> ProjectVersion:
        return ProjectVersion(**value)

    def _inventory(self, root: Path) -> dict[str, dict]:
        files: dict[str, dict] = {}
        for source in sorted(root.rglob("*")):
            relative = source.relative_to(root)
            if self._is_protected(relative) or source.is_symlink() or not source.is_file():
                continue
            files[relative.as_posix()] = {"sha256": self._digest(source), "size": source.stat().st_size}
        return files

    def capture(
        self,
        project_id: str,
        label: Optional[str] = None,
        reason: str = "manual",
        execution_id: Optional[str] = None,
        tenant_id: str = "local",
    ) -> ProjectVersion:
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        with self._lock:
            self._assert_no_symlinks(root)
            bucket = self._bucket(project_id, tenant_id)
            version_id = uuid.uuid4().hex[:16]
            temporary = bucket / (version_id + ".tmp")
            destination = bucket / version_id
            files_root = temporary / "files"
            files_root.mkdir(parents=True, exist_ok=False)
            inventory: dict[str, dict] = {}
            try:
                sources = []
                total_bytes = 0
                for source in sorted(root.rglob("*")):
                    relative = source.relative_to(root)
                    if self._is_protected(relative) or source.is_symlink() or not source.is_file():
                        continue
                    sources.append((source, relative))
                    total_bytes += source.stat().st_size
                    if len(sources) > MAX_VERSION_FILES or total_bytes > MAX_VERSION_BYTES:
                        raise ValueError("project is too large to version safely")
                for source, relative in sources:
                    target = files_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    inventory[relative.as_posix()] = {"sha256": self._digest(target), "size": target.stat().st_size}
                record = ProjectVersion(
                    version_id=version_id,
                    project_id=project_id,
                    label=self._clean_label(label, "Versão %s" % time.strftime("%d/%m %H:%M")),
                    reason=str(reason)[:40],
                    created_at=time.time(),
                    file_count=len(inventory),
                    size_bytes=sum(item["size"] for item in inventory.values()),
                    execution_id=execution_id,
                )
                (temporary / "snapshot.json").write_text(
                    json.dumps({"record": asdict(record), "files": inventory}, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                temporary.replace(destination)
                records = self._load_index(bucket)
                records[version_id] = asdict(record)
                self._save_index(bucket, records)
                return record
            except Exception:
                if temporary.is_dir():
                    shutil.rmtree(temporary)
                if destination.is_dir():
                    shutil.rmtree(destination)
                raise

    def publish_execution(
        self,
        project_id: str,
        execution_id: str,
        files: list[str],
        tenant_id: str = "local",
    ) -> tuple[tuple[str, ...], ProjectVersion, ProjectVersion]:
        """Version and publish one execution as a single serialized operation."""
        with self._lock:
            before = self.capture(
                project_id,
                label="Backup antes da missão",
                reason="pre_publish",
                execution_id=execution_id,
                tenant_id=tenant_id,
            )
            promoted = self.projects.promote_execution_files(
                project_id,
                execution_id,
                files,
                tenant_id=tenant_id,
            )
            after = self.capture(
                project_id,
                label="Resultado da missão",
                reason="mission",
                execution_id=execution_id,
                tenant_id=tenant_id,
            )
            return promoted, before, after

    def list(self, project_id: str, tenant_id: str = "local") -> list[ProjectVersion]:
        with self._lock:
            self.projects.project_root(project_id, tenant_id=tenant_id)
            bucket = self._bucket(project_id, tenant_id)
            values = [self._record(value) for value in self._load_index(bucket).values()]
            return sorted(values, key=lambda item: item.created_at, reverse=True)

    def _snapshot(self, project_id: str, version_id: str, tenant_id: str) -> tuple[ProjectVersion, Path, dict[str, dict]]:
        bucket = self._bucket(project_id, tenant_id)
        value = self._load_index(bucket).get(version_id)
        if value is None:
            raise KeyError("version not found")
        record = self._record(value)
        snapshot_root = (bucket / version_id / "files").resolve()
        snapshot_root.relative_to(bucket)
        metadata = bucket / version_id / "snapshot.json"
        if not snapshot_root.is_dir() or not metadata.is_file():
            raise ValueError("version data is incomplete")
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        files = payload.get("files")
        if not isinstance(files, dict):
            raise ValueError("version manifest is invalid")
        return record, snapshot_root, files

    def compare(
        self,
        project_id: str,
        version_id: str,
        against_version_id: Optional[str] = None,
        tenant_id: str = "local",
    ) -> dict[str, list[str]]:
        with self._lock:
            root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
            _, _, selected = self._snapshot(project_id, version_id, tenant_id)
            if against_version_id:
                _, _, baseline = self._snapshot(project_id, against_version_id, tenant_id)
            else:
                baseline = self._inventory(root)
            selected_names = set(selected)
            baseline_names = set(baseline)
            return {
                "added": sorted(selected_names - baseline_names),
                "modified": sorted(name for name in selected_names & baseline_names if selected[name]["sha256"] != baseline[name]["sha256"]),
                "deleted": sorted(baseline_names - selected_names),
            }

    def restore(self, project_id: str, version_id: str, tenant_id: str = "local") -> tuple[ProjectVersion, ProjectVersion]:
        root = self.projects.project_root(project_id, tenant_id=tenant_id).resolve()
        with self._lock:
            self._assert_no_symlinks(root)
            selected, snapshot_root, manifest = self._snapshot(project_id, version_id, tenant_id)
            for item in snapshot_root.rglob("*"):
                relative = item.relative_to(snapshot_root)
                if item.is_symlink() or self._is_protected(relative):
                    raise ValueError("version integrity check failed")
            if self._inventory(snapshot_root) != manifest:
                raise ValueError("version integrity check failed")
            for relative_name, expected in manifest.items():
                relative = Path(PurePosixPath(relative_name))
                source = (snapshot_root / relative).resolve()
                source.relative_to(snapshot_root)
                if (
                    self._is_protected(relative)
                    or not isinstance(expected, dict)
                    or not source.is_file()
                    or self._digest(source) != expected.get("sha256")
                    or source.stat().st_size != expected.get("size")
                ):
                    raise ValueError("version integrity check failed")

            safety = self.capture(
                project_id,
                label="Backup antes da restauração",
                reason="pre_restore",
                tenant_id=tenant_id,
            )
            bucket = self._bucket(project_id, tenant_id)
            transaction_id = uuid.uuid4().hex[:12]
            stage = bucket / ("restore-stage-" + transaction_id)
            previous = bucket / ("restore-previous-" + transaction_id)
            preserved = bucket / ("restore-preserved-" + transaction_id)
            shutil.copytree(snapshot_root, stage)
            previous.mkdir()
            preserved.mkdir()
            for source in root.rglob("*"):
                relative = source.relative_to(root)
                if source.is_file() and any(part == ".env" or part.startswith(".env.") for part in relative.parts):
                    target = preserved / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            moved: list[Path] = []
            installed: list[Path] = []
            try:
                for child in list(root.iterdir()):
                    if self._is_protected(Path(child.name)):
                        continue
                    child.replace(previous / child.name)
                    moved.append(child)
                for child in list(stage.iterdir()):
                    target = root / child.name
                    child.replace(target)
                    installed.append(target)
                for source in preserved.rglob("*"):
                    if not source.is_file():
                        continue
                    target = root / source.relative_to(preserved)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                actual = self._inventory(root)
                if actual != manifest:
                    raise ValueError("restored version verification failed")
            except Exception:
                for target in reversed(installed):
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.exists():
                        target.unlink()
                for original in reversed(moved):
                    backup = previous / original.name
                    if backup.exists():
                        backup.replace(root / original.name)
                raise
            finally:
                if stage.is_dir():
                    shutil.rmtree(stage)
                if previous.is_dir():
                    shutil.rmtree(previous)
                if preserved.is_dir():
                    shutil.rmtree(preserved)
            return selected, safety
