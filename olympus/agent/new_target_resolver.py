import re
from pathlib import Path


class NewTargetResolutionError(ValueError):
    pass


_PATTERNS = (
    r"fun[cç][aã]o\s+(?:python\s+)?(?:chamada\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
    r"class[e]?\s+(?:python\s+)?(?:chamada\s+)?([A-Za-z_][A-Za-z0-9_]*)",
)


def resolve_new_target(task: str) -> str:
    text = task.strip()

    explicit = re.search(
        r"(?<![A-Za-z0-9_])((?:olympus|tests|scripts)/[A-Za-z0-9_./-]+)",
        text,
    )

    if explicit:
        target = explicit.group(1).rstrip(".,;:)")

        if (
            target.startswith("/")
            or ".." in Path(target).parts
        ):
            raise NewTargetResolutionError(
                "unsafe explicit target"
            )

        return target

    for pattern in _PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            symbol = match.group(1)

            if not re.match(
                r"^[A-Za-z_][A-Za-z0-9_]*$",
                symbol,
            ):
                raise NewTargetResolutionError(
                    "unsafe symbol"
                )

            return "olympus/agent/%s.py" % symbol.lower()

    raise NewTargetResolutionError(
        "target cannot be safely inferred"
    )
