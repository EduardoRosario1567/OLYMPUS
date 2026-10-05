from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

from olympus.agent.safe_apply import SafeApplyError, apply
from olympus.routing.interfaces import RoutingAdapter


@dataclass(frozen=True)
class DevAgentResult:
    success: bool
    task: str
    requested_model: str
    actual_model: Optional[str]
    provider: Optional[str]
    files_modified: Tuple[str, ...]
    execution_status: str
    latency_ms: int
    error: Optional[str]


class OlympusDevAgent:
    def __init__(
        self,
        router: RoutingAdapter,
        model_id: str,
        root: str,
    ) -> None:
        self.router = router
        self.model_id = model_id
        self.root = str(Path(root).resolve())

    def run(
        self,
        task: str,
        target: str,
        allowed_paths: Sequence[str],
        timeout_hint: Optional[int] = None,
    ) -> DevAgentResult:

        prompt = (
            "Complete ONE small coding task.\n"
            "Return exactly ONE file block.\n\n"
            "FORMAT:\n"
            "=== FILE: %s ===\n"
            "<raw file content>\n\n"
            "RULES:\n"
            "- no markdown fences\n"
            "- no explanations\n"
            "- no additional files\n"
            "- Python 3.9 compatible\n\n"
            "TASK:\n%s"
        ) % (target, task)

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
            return DevAgentResult(
                success=False,
                task=task,
                requested_model=self.model_id,
                actual_model=result.actual_model,
                provider=result.provider,
                files_modified=tuple(),
                execution_status=status,
                latency_ms=int(result.latency_ms or 0),
                error=result.error,
            )

        try:
            applied = apply(
                root=self.root,
                payload=result.output,
                allowed_paths=allowed_paths,
            )
        except SafeApplyError as exc:
            return DevAgentResult(
                success=False,
                task=task,
                requested_model=self.model_id,
                actual_model=result.actual_model,
                provider=result.provider,
                files_modified=tuple(),
                execution_status="blocked",
                latency_ms=int(result.latency_ms or 0),
                error=str(exc),
            )

        return DevAgentResult(
            success=True,
            task=task,
            requested_model=self.model_id,
            actual_model=result.actual_model,
            provider=result.provider,
            files_modified=applied.applied_files,
            execution_status=status,
            latency_ms=int(result.latency_ms or 0),
            error=None,
        )
