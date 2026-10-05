from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable


class SafeApplyError(ValueError):
    """Raised when a patch violates the safe-apply contract."""


@dataclass(frozen=True)
class ApplyResult:
    applied_files: tuple
    rejected_files: tuple


def _normalize_relative_path(path: str) -> str:
    if not path or not path.strip():
        raise SafeApplyError("empty path")

    raw = path.replace("\\", "/").strip()

    if raw.startswith("/"):
        raise SafeApplyError("absolute path is forbidden")

    parts = Path(raw).parts

    if ".." in parts:
        raise SafeApplyError("path traversal is forbidden")

    normalized = "/".join(parts)

    if normalized.startswith("./"):
        normalized = normalized[2:]

    if not normalized:
        raise SafeApplyError("invalid path")

    return normalized


def _is_allowed(path: str, allowed_paths: Iterable[str]) -> bool:
    normalized = _normalize_relative_path(path)

    for allowed in allowed_paths:
        allowed_normalized = _normalize_relative_path(allowed)

        if normalized == allowed_normalized:
            return True

        if allowed_normalized.endswith("/"):
            if normalized.startswith(allowed_normalized):
                return True

        if normalized.startswith(allowed_normalized + "/"):
            return True

    return False


def parse_file_blocks(payload: str) -> Dict[str, str]:
    """
    Parse:
    === FILE: path ===
    content
    === FILE: path ===
    content
    """
    if not payload or not payload.strip():
        raise SafeApplyError("empty payload")

    lines = payload.splitlines()
    blocks = {}
    current_path = None
    current_content = []

    def flush():
        nonlocal current_path, current_content
        if current_path is not None:
            if current_path in blocks:
                raise SafeApplyError("duplicate file path: %s" % current_path)
            blocks[current_path] = "\n".join(current_content).rstrip() + "\n"
        current_path = None
        current_content = []

    for line in lines:
        if line.startswith("=== FILE: ") and line.endswith(" ==="):
            flush()
            current_path = line[len("=== FILE: "):-len(" ===")]
        elif current_path is not None:
            current_content.append(line)
        elif line.strip():
            raise SafeApplyError("content outside file block")

    flush()

    if not blocks:
        raise SafeApplyError("no file blocks found")

    return blocks


def apply(
    root: str,
    payload: str,
    allowed_paths: Iterable[str],
) -> ApplyResult:
    """
    Apply generated files only inside the explicit allowlist.

    No deletion.
    No shell execution.
    No dependency installation.
    """
    root_path = Path(root).resolve()
    allowed = tuple(allowed_paths)

    blocks = parse_file_blocks(payload)

    for path in blocks:
        if not _is_allowed(path, allowed):
            raise SafeApplyError("path not allowed: %s" % path)

    applied = []

    for relative_path, content in blocks.items():
        normalized = _normalize_relative_path(relative_path)
        destination = (root_path / normalized).resolve()

        try:
            destination.relative_to(root_path)
        except ValueError:
            raise SafeApplyError(
                "destination escapes repository: %s" % relative_path
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        applied.append(normalized)

    return ApplyResult(
        applied_files=tuple(applied),
        rejected_files=tuple(),
    )
