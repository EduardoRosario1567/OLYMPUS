import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from olympus.agent.safe_edit import SafeEditError, apply_edit
from olympus.routing.interfaces import RoutingAdapter


@dataclass(frozen=True)
class EditAgentResult:
    success: bool
    files_modified: Tuple[str, ...]
    actual_model: Optional[str]
    provider: Optional[str]
    latency_ms: int
    execution_status: str
    error: Optional[str]


class OlympusEditAgent:

    def __init__(
        self,
        router: RoutingAdapter,
        model_id: str,
        root: str,
    ) -> None:
        self.router = router
        self.model_id = model_id
        self.root = str(Path(root).resolve())

    @staticmethod
    def _parse(payload: str):
        search_tag = "=== SEARCH ==="
        replace_tag = "=== REPLACE ==="
        end_tag = "=== END ==="

        if not all(
            tag in payload
            for tag in (search_tag, replace_tag, end_tag)
        ):
            raise SafeEditError("invalid edit protocol")

        before, rest = payload.split(search_tag, 1)
        search, rest = rest.split(replace_tag, 1)
        replace, after = rest.split(end_tag, 1)

        if before.strip() or after.strip():
            raise SafeEditError("content outside edit protocol")

        search = search.strip("\n")
        replace = replace.strip("\n")

        if not search:
            raise SafeEditError("empty search")

        return search, replace

    @staticmethod
    def _relevant_context(source: str, task: str) -> str:
        lines = source.splitlines()

        words = [
            word.lower()
            for word in re.findall(
                r"[A-Za-z_][A-Za-z0-9_]{3,}",
                task,
            )
        ]

        # Find the first genuinely relevant symbol/identifier.
        hits = []

        for index, line in enumerate(lines):
            lower = line.lower()

            if any(
                word in lower
                for word in words
                if len(word) >= 5
            ):
                hits.append(index)

        if not hits:
            return "\n".join(lines[:25])

        center = hits[0]
        start = max(0, center - 8)
        end = min(len(lines), center + 9)

        return "\n".join(lines[start:end])

    def run(
        self,
        task: str,
        target: str,
    ) -> EditAgentResult:

        path = Path(self.root) / target

        if not path.is_file():
            return EditAgentResult(
                False,
                tuple(),
                None,
                None,
                0,
                "blocked",
                "existing target not found",
            )

        source = path.read_text(encoding="utf-8")

        context = self._relevant_context(
            source,
            task,
        )

        prompt = (
            "Make ONE minimal edit.\n\n"
            "TASK:\n%s\n\n"
            "TARGET: %s\n\n"
            "RELEVANT CODE ONLY:\n"
            "%s\n\n"
            "Return ONLY this protocol:\n"
            "=== SEARCH ===\n"
            "<exact existing lines>\n"
            "=== REPLACE ===\n"
            "<replacement lines>\n"
            "=== END ===\n\n"
            "Constraints:\n"
            "- SEARCH must occur exactly once in the real file\n"
            "- smallest possible change\n"
            "- preserve unrelated behavior\n"
            "- Python 3.9\n"
            "- no explanation\n"
            "- no markdown\n"
        ) % (task, target, context)

        result = self.router.execute(
            self.model_id,
            prompt,
        )

        status = getattr(
            result.status,
            "value",
            result.status or "",
        )

        if not result.success:
            return EditAgentResult(
                False,
                tuple(),
                result.actual_model,
                result.provider,
                int(result.latency_ms or 0),
                status,
                result.error,
            )

        try:
            search, replace = self._parse(
                result.output
            )

            applied = apply_edit(
                root=self.root,
                relative_path=target,
                search=search,
                replace=replace,
                allowed_paths=[target],
            )

        except SafeEditError as exc:
            return EditAgentResult(
                False,
                tuple(),
                result.actual_model,
                result.provider,
                int(result.latency_ms or 0),
                "blocked",
                str(exc),
            )

        return EditAgentResult(
            True,
            (applied.file,),
            result.actual_model,
            result.provider,
            int(result.latency_ms or 0),
            status,
            None,
        )
