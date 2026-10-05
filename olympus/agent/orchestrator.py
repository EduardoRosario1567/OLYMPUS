from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

from olympus.agent.dev_agent import OlympusDevAgent
from olympus.agent.edit_agent import OlympusEditAgent
from olympus.agent.repair_loop import RepairLoop
from olympus.agent.test_runner import TargetedTestRunner
from olympus.routing.interfaces import RoutingAdapter


@dataclass(frozen=True)
class AgentRunResult:
    success: bool
    task: str
    requested_model: str
    actual_model: Optional[str]
    provider: Optional[str]
    files_modified: Tuple[str, ...]
    tests_run: Tuple[str, ...]
    tests_passed: bool
    repair_cycles: int
    execution_status: str
    latency_ms: int
    error: Optional[str]


class OlympusAgent:
    def __init__(
        self,
        router: RoutingAdapter,
        model_id: str,
        root: str,
    ) -> None:
        self.root = str(Path(root).resolve())
        self.dev_agent = OlympusDevAgent(
            router=router,
            model_id=model_id,
            root=self.root,
        )
        self.test_runner = TargetedTestRunner()

    def run(
        self,
        task: str,
        target: str,
        allowed_paths: Sequence[str],
        test_modules: Sequence[str],
    ) -> AgentRunResult:

        target_path = Path(self.root) / target

        if target_path.is_file():
            edit_agent = OlympusEditAgent(
                router=self.dev_agent.router,
                model_id=self.dev_agent.model_id,
                root=self.root,
            )

            edit_result = edit_agent.run(
                task=task,
                target=target,
            )

            if not edit_result.success:
                return AgentRunResult(
                    success=False,
                    task=task,
                    requested_model=self.dev_agent.model_id,
                    actual_model=edit_result.actual_model,
                    provider=edit_result.provider,
                    files_modified=edit_result.files_modified,
                    tests_run=tuple(),
                    tests_passed=False,
                    repair_cycles=0,
                    execution_status=edit_result.execution_status,
                    latency_ms=edit_result.latency_ms,
                    error=edit_result.error,
                )

            development = type(
                "DevelopmentResult",
                (),
                {
                    "success": True,
                    "requested_model": self.dev_agent.model_id,
                    "actual_model": edit_result.actual_model,
                    "provider": edit_result.provider,
                    "files_modified": edit_result.files_modified,
                    "execution_status": edit_result.execution_status,
                    "latency_ms": edit_result.latency_ms,
                    "error": None,
                },
            )()
        else:
            development = self.dev_agent.run(
                task=task,
                target=target,
                allowed_paths=allowed_paths,
            )

        if not development.success:
            return AgentRunResult(
                success=False,
                task=task,
                requested_model=development.requested_model,
                actual_model=development.actual_model,
                provider=development.provider,
                files_modified=development.files_modified,
                tests_run=tuple(),
                tests_passed=False,
                repair_cycles=0,
                execution_status=development.execution_status,
                latency_ms=development.latency_ms,
                error=development.error,
            )

        if not test_modules:
            target_path = Path(self.root) / target

            if target_path.suffix == ".py" and target_path.is_file():
                import py_compile

                try:
                    py_compile.compile(
                        str(target_path),
                        doraise=True,
                    )

                    class SyntaxResult:
                        success = True
                        stdout = ""
                        stderr = ""

                    tests = SyntaxResult()
                except Exception as exc:

                    class SyntaxResult:
                        success = False
                        stdout = ""
                        stderr = str(exc)

                    tests = SyntaxResult()
            else:
                raise ValueError(
                    "no validation strategy available"
                )
        else:
            tests = self.test_runner.run_unittest(test_modules)

        if not tests.success:
            error = tests.stderr or tests.stdout or "tests failed"

            repair = RepairLoop(
                router=self.dev_agent.router,
                model_id=self.dev_agent.model_id,
                root=self.root,
                max_cycles=3,
            )

            repair_result = repair.repair(
                task=task,
                target=target,
                allowed_paths=allowed_paths,
                test_modules=test_modules,
                initial_error=error,
            )

            files = tuple(
                dict.fromkeys(
                    development.files_modified
                    + repair_result.files_modified
                )
            )

            return AgentRunResult(
                success=repair_result.success,
                task=task,
                requested_model=development.requested_model,
                actual_model=development.actual_model,
                provider=development.provider,
                files_modified=files,
                tests_run=tuple(test_modules),
                tests_passed=repair_result.tests_passed,
                repair_cycles=repair_result.cycles,
                execution_status=development.execution_status,
                latency_ms=development.latency_ms,
                error=repair_result.error,
            )

        return AgentRunResult(
            success=True,
            task=task,
            requested_model=development.requested_model,
            actual_model=development.actual_model,
            provider=development.provider,
            files_modified=development.files_modified,
            tests_run=tuple(test_modules),
            tests_passed=True,
            repair_cycles=0,
            execution_status=development.execution_status,
            latency_ms=development.latency_ms,
            error=None,
        )
