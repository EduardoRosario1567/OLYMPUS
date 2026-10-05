from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

from olympus.agent.safe_apply import SafeApplyError, apply
from olympus.agent.test_runner import TargetedTestRunner
from olympus.routing.interfaces import RoutingAdapter


@dataclass(frozen=True)
class RepairResult:
    success: bool
    cycles: int
    files_modified: Tuple[str, ...]
    tests_passed: bool
    error: Optional[str]


class RepairLoop:
    def __init__(
        self,
        router: RoutingAdapter,
        model_id: str,
        root: str,
        max_cycles: int = 3,
    ) -> None:
        if max_cycles < 1 or max_cycles > 3:
            raise ValueError("max_cycles must be between 1 and 3")

        self.router = router
        self.model_id = model_id
        self.root = str(Path(root).resolve())
        self.max_cycles = max_cycles
        self.test_runner = TargetedTestRunner()

    def repair(
        self,
        task: str,
        target: str,
        allowed_paths: Sequence[str],
        test_modules: Sequence[str],
        initial_error: str,
    ) -> RepairResult:

        error = initial_error
        modified = []

        for cycle in range(1, self.max_cycles + 1):
            target_path = Path(self.root) / target

            if not target_path.is_file():
                return RepairResult(
                    False, cycle - 1, tuple(modified), False,
                    "target file not found",
                )

            source = target_path.read_text(encoding="utf-8")

            prompt = (
                "Repair ONE Python file.\n"
                "Return exactly ONE file block.\n\n"
                "=== FILE: %s ===\n"
                "<complete corrected file>\n\n"
                "TASK:\n%s\n\n"
                "CURRENT FILE:\n%s\n\n"
                "TEST FAILURE:\n%s\n\n"
                "RULES:\n"
                "- fix only what is required by the failing test\n"
                "- preserve unrelated behavior\n"
                "- Python 3.9\n"
                "- no explanation\n"
                "- no markdown\n"
                "- no additional files\n"
            ) % (target, task, source, error[-4000:])

            execution = self.router.execute(
                self.model_id,
                prompt,
            )

            if not execution.success:
                error = execution.error or "repair execution failed"
                continue

            try:
                applied = apply(
                    root=self.root,
                    payload=execution.output,
                    allowed_paths=allowed_paths,
                )
            except SafeApplyError as exc:
                error = str(exc)
                continue

            modified.extend(applied.applied_files)

            tests = self.test_runner.run_unittest(test_modules)

            if tests.success:
                return RepairResult(
                    success=True,
                    cycles=cycle,
                    files_modified=tuple(modified),
                    tests_passed=True,
                    error=None,
                )

            error = tests.stderr or tests.stdout or "tests failed"

        return RepairResult(
            success=False,
            cycles=self.max_cycles,
            files_modified=tuple(modified),
            tests_passed=False,
            error=error,
        )
