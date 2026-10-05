from pathlib import Path


AGENT_FALLBACK_TEST = "tests.test_safe_apply"


def resolve_test_module(root: str, target: str) -> str:
    root_path = Path(root).resolve()
    target_path = Path(target)

    if target_path.is_absolute() or ".." in target_path.parts:
        raise ValueError("unsafe target path")

    stem = target_path.stem

    candidate = root_path / "tests" / ("test_%s.py" % stem)

    if candidate.is_file():
        return "tests.test_%s" % stem

    if target.startswith("olympus/agent/"):
        return AGENT_FALLBACK_TEST

    if target.startswith("scripts/") and target.endswith(".sh"):
        return "shell:%s" % target

    raise ValueError(
        "no safe targeted test could be resolved for %s" % target
    )
