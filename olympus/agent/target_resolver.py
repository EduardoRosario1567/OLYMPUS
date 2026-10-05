from pathlib import Path
from typing import Iterable, List


class TargetResolutionError(ValueError):
    pass


def _safe(path: str) -> bool:
    p = Path(path)
    return (
        bool(path)
        and not p.is_absolute()
        and ".." not in p.parts
        and (
            path.startswith("olympus/")
            or path.startswith("tests/")
        )
    )


def _normalize(value: str) -> str:
    return (
        value.lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("/", " ")
        .strip()
    )


def resolve_target(
    root: str,
    task: str,
    candidates: Iterable[str],
) -> str:
    """
    Deterministically resolve a target from explicit candidate paths.

    Priority:
    1. exact filename mention
    2. normalized stem mention
    3. unique candidate
    Otherwise raises.
    """
    task_norm = _normalize(task)
    valid: List[str] = [c for c in candidates if _safe(c)]

    if not valid:
        raise TargetResolutionError("no safe candidates")

    exact = [
        c
        for c in valid
        if _normalize(Path(c).name) in task_norm
    ]

    if len(exact) == 1:
        return exact[0]

    matches = []
    for candidate in valid:
        stem = _normalize(Path(candidate).stem)
        words = [w for w in stem.split() if w]

        if words and all(word in task_norm for word in words):
            matches.append(candidate)

    if len(matches) == 1:
        return matches[0]

    if len(valid) == 1:
        return valid[0]

    raise TargetResolutionError(
        "target ambiguous; explicit target required"
    )
