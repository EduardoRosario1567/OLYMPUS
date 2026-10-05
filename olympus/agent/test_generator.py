from pathlib import Path
from typing import Optional

from olympus.agent.safe_apply import SafeApplyError, apply
from olympus.routing.interfaces import RoutingAdapter


class TestGenerationError(RuntimeError):
    pass


class AcceptanceTestGenerator:

    def __init__(
        self,
        router: RoutingAdapter,
        model_id: str,
        root: str,
    ) -> None:
        self.router = router
        self.model_id = model_id
        self.root = str(Path(root).resolve())

    def generate(
        self,
        task: str,
        target: str,
    ) -> str:

        target_path = Path(target)

        if (
            target_path.is_absolute()
            or ".." in target_path.parts
            or target_path.suffix != ".py"
        ):
            raise TestGenerationError("unsafe target")

        test_name = "test_%s.py" % target_path.stem
        test_path = "tests/%s" % test_name

        prompt = (
            "Create ONE minimal Python unittest file.\n"
            "The test must validate ONLY the explicit requirement.\n"
            "Do not invent unspecified behavior.\n\n"
            "IMPLEMENTATION TARGET:\n%s\n\n"
            "REQUIREMENT:\n%s\n\n"
            "Return exactly:\n"
            "=== FILE: %s ===\n"
            "<raw Python unittest source>\n\n"
            "Rules:\n"
            "- Python 3.9\n"
            "- unittest only\n"
            "- no markdown\n"
            "- no explanation\n"
            "- one test file only\n"
        ) % (target, task, test_path)

        result = self.router.execute(
            self.model_id,
            prompt,
        )

        if not result.success:
            raise TestGenerationError(
                result.error or "test generation failed"
            )

        try:
            applied = apply(
                root=self.root,
                payload=result.output,
                allowed_paths=[test_path],
            )
        except SafeApplyError as exc:
            raise TestGenerationError(str(exc))

        if applied.applied_files != (test_path,):
            raise TestGenerationError(
                "unexpected generated files"
            )

        return "tests.test_%s" % target_path.stem
