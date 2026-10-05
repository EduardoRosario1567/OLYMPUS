from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from olympus.agent.safe_apply import SafeApplyError, _is_allowed


class SafeEditError(ValueError):
    pass


@dataclass(frozen=True)
class EditResult:
    file: str
    replacements: int


def apply_edit(
    root: str,
    relative_path: str,
    search: str,
    replace: str,
    allowed_paths: Iterable[str],
) -> EditResult:

    if not _is_allowed(relative_path, allowed_paths):
        raise SafeEditError("path not allowed: %s" % relative_path)

    root_path = Path(root).resolve()
    target = (root_path / relative_path).resolve()

    try:
        target.relative_to(root_path)
    except ValueError:
        raise SafeEditError("destination escapes repository")

    if not target.is_file():
        raise SafeEditError("target file not found")

    if not search:
        raise SafeEditError("empty search block")

    content = target.read_text(encoding="utf-8")
    count = content.count(search)

    if count == 0:
        raise SafeEditError("search block not found")

    if count > 1:
        raise SafeEditError(
            "search block is ambiguous: %d matches" % count
        )

    updated = content.replace(search, replace, 1)
    target.write_text(updated, encoding="utf-8")

    return EditResult(
        file=relative_path,
        replacements=1,
    )
