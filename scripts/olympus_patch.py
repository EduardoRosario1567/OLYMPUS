import argparse
import sys
import tempfile
from pathlib import Path

from olympus.agent.safe_apply import SafeApplyError, apply
from olympus.routing.omniroute_adapter import OmniRouteAdapter


DEFAULT_MODEL = "openrouter/openrouter/free"
DEFAULT_URL = "http://127.0.0.1:20128"


def build_prompt(task: str, target: str) -> str:
    return (
        "Complete one small coding task.\n"
        "Return exactly one file block.\n\n"
        "FORMAT:\n"
        "=== FILE: %s ===\n"
        "<raw file content>\n\n"
        "RULES:\n"
        "- no markdown fences\n"
        "- no explanation\n"
        "- no additional files\n"
        "- Python 3.9 compatible\n\n"
        "TASK:\n%s"
    ) % (target, task)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OLYMPUS structured patch runner"
    )
    parser.add_argument("task")
    parser.add_argument("--target", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    router = OmniRouteAdapter(
        base_url=DEFAULT_URL,
        timeout_seconds=args.timeout,
    )

    result = router.execute(
        DEFAULT_MODEL,
        build_prompt(args.task, args.target),
    )

    print("SUCCESS:", result.success)
    print("MODEL:", result.actual_model or "")
    print("LATENCY_MS:", result.latency_ms)

    if not result.success:
        print("ERROR:", result.error or "")
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp:
            applied = apply(
                root=tmp,
                payload=result.output,
                allowed_paths=[args.target],
            )

            target = Path(tmp) / args.target

            print("PATCH_VALID: True")
            print("FILES:", ",".join(applied.applied_files))
            print()
            print(target.read_text(encoding="utf-8"))

    except SafeApplyError as exc:
        print("PATCH_VALID: False")
        print("ERROR:", str(exc))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
