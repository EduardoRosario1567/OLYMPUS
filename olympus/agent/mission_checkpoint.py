from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import os
import shutil
import tempfile
import time
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class MissionCheckpoint:
    mission_id: str
    completed_step_ids: Tuple[str, ...] = ()
    active_step_id: Optional[str] = None
    status: str = "running"
    models_attempted: Tuple[str, ...] = ()
    files_modified: Tuple[str, ...] = ()
    tests_run: Tuple[str, ...] = ()
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    files_read: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["metadata"] = dict(self.metadata or {})
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "MissionCheckpoint":
        return cls(
            mission_id=str(data["mission_id"]),
            completed_step_ids=tuple(data.get("completed_step_ids") or ()),
            active_step_id=data.get("active_step_id"),
            status=str(data.get("status") or "running"),
            models_attempted=tuple(data.get("models_attempted") or ()),
            files_modified=tuple(data.get("files_modified") or ()),
            tests_run=tuple(data.get("tests_run") or ()),
            files_read=tuple(data.get("files_read") or ()),
            last_error=data.get("last_error"),
            metadata=dict(data.get("metadata") or {}),
        )


class MissionCheckpointStore:
    """Atomic JSON checkpoints for safe mission-level resume.

    A step is only marked completed after AgentLoop has verified it. An interrupted
    active step resumes from a compact action-boundary continuation. Verified
    mutations carry stable idempotency keys, so another model cannot apply the
    same successful mutation twice. Completed steps are never replayed.
    """

    def __init__(self, root: str, directory: str = ".olympus/checkpoints") -> None:
        self.root = Path(root).resolve()
        self.directory = self.root / directory

    @staticmethod
    def _safe_id(mission_id: str) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in mission_id)

    def path_for(self, mission_id: str) -> Path:
        return self.directory / (self._safe_id(mission_id) + ".json")

    def load(self, mission_id: str) -> Optional[MissionCheckpoint]:
        path = self.path_for(mission_id)
        if not path.is_file():
            return None
        try:
            return MissionCheckpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError):
            backup = path.with_suffix(path.suffix + ".bak")
            try:
                if backup.is_file():
                    return MissionCheckpoint.from_dict(json.loads(backup.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, KeyError):
                pass
            # Do not silently replay a possibly half-written mission. Keep the
            # corrupt evidence for diagnosis and start without unsafe state.
            try:
                quarantine = path.with_name("%s.corrupt.%d" % (path.name, int(time.time())))
                os.replace(path, quarantine)
            except OSError:
                pass
            return None

    def save(self, checkpoint: MissionCheckpoint) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.path_for(checkpoint.mission_id)
        backup = target.with_suffix(target.suffix + ".bak")
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", dir=str(self.directory))
        try:
            if target.is_file():
                shutil.copy2(target, backup)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(checkpoint.to_dict(), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return target

    def clear(self, mission_id: str) -> None:
        path = self.path_for(mission_id)
        if path.exists():
            path.unlink()
