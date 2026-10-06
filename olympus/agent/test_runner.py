import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from typing import Sequence, Tuple
from olympus.agent.output_compactor import compact_output
from olympus.agent.container_execution import ContainerExecutor


@dataclass(frozen=True)
class TestRunResult:
    success: bool
    command: Tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class TargetedTestRunner:
    """
    Runs only explicitly supplied Python unittest modules.

    No shell.
    Project test modules are executable code. Execution requires a local
    container runtime and an approved image; no host fallback is allowed.
    """

    def __init__(self, cwd: Optional[str] = None) -> None:
        self.cwd = str(Path(cwd).resolve()) if cwd else None

    def run_unittest(
        self,
        test_modules: Sequence[str],
        timeout_seconds: int = 60,
    ) -> TestRunResult:

        if not test_modules:
            raise ValueError("at least one test module is required")

        if len(test_modules) == 1 and test_modules[0].startswith("shell:"):
            target = test_modules[0][len("shell:"):]

            if (
                not target.startswith("scripts/")
                or not target.endswith(".sh")
                or ".." in target
                or any(c in target for c in (";", "&", "|", "\\"))
            ):
                raise ValueError("unsafe shell validation target")

            command = ("zsh", "-n", target)

            process = self._run(command, timeout_seconds)

            stdout = compact_output(process.stdout)
            stderr = compact_output(process.stderr)
            return TestRunResult(
                success=process.returncode == 0,
                command=command,
                returncode=process.returncode,
                stdout=stdout.text,
                stderr=stderr.text,
            )

        for module in test_modules:
            if not module.startswith("tests."):
                raise ValueError(
                    "only tests.* modules are allowed"
                )

            if any(
                token in module
                for token in ("..", "/", "\\", ";", "&", "|")
            ):
                raise ValueError(
                    "unsafe test module: %s" % module
                )

        command = (
            sys.executable,
            "-m",
            "unittest",
            *test_modules,
            "-v",
        )

        try:
            process = self._run(command, timeout_seconds)

            # A module can call sys.exit(0) during import and terminate
            # unittest before a suite runs. Exit status alone is not evidence.
            completed = re.search(r"^Ran ([1-9][0-9]*) tests? in ", process.stderr, re.M)
            skipped = re.search(r"^OK \(skipped=([0-9]+)\)", process.stderr, re.M)
            executed = int(completed.group(1)) if completed else 0
            if skipped:
                executed -= int(skipped.group(1))
            evidence = executed > 0 and bool(re.search(r"^OK(?:\s|\(|$)", process.stderr, re.M))
            success = process.returncode == 0 and evidence
            diagnostic = process.stderr
            if process.returncode == 0 and not evidence:
                diagnostic += (
                    "\nunittest evidence missing: no completed nonempty test run. "
                    "Define unittest.TestCase methods; do not exit the interpreter while importing tests.\n"
                )
            stdout = compact_output(process.stdout)
            stderr = compact_output(diagnostic)
            return TestRunResult(
                success=success,
                command=tuple(command),
                returncode=process.returncode,
                stdout=stdout.text,
                stderr=stderr.text,
            )

        except subprocess.TimeoutExpired as exc:
            return TestRunResult(
                success=False,
                command=tuple(command),
                returncode=124,
                stdout=compact_output(exc.stdout or "").text,
                stderr=compact_output(exc.stderr or "test timeout").text,
            )

    def _run(self, command: Tuple[str, ...], timeout_seconds: int):
        return ContainerExecutor().run(self.cwd or os.getcwd(), command, timeout_seconds)
