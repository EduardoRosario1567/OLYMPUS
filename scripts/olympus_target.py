import argparse
import os
import sys

from olympus.agent.target_resolver import (
    TargetResolutionError,
    validate_target,
)
from olympus.routing.omniroute_adapter import OmniRouteAdapter


MODEL = "openrouter/openrouter/free"
URL = "http://127.0.0.1:20128"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()

    prompt = (
        "Choose exactly ONE project-relative Python file path "
        "for this coding task.\n"
        "Allowed roots: olympus/ or tests/.\n"
        "Return ONLY the path. No explanation.\n\n"
        "TASK:\n%s" % args.task
    )

    router = OmniRouteAdapter(
        base_url=URL,
        timeout_seconds=args.timeout,
    )

    result = router.execute(MODEL, prompt)

    if not result.success:
        print("ERROR:", result.error, file=sys.stderr)
        return 1

    candidate = result.output.strip().strip("`")

    try:
        target = validate_target(
            os.getcwd(),
            candidate,
        )
    except TargetResolutionError as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 2

    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
