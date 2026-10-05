import argparse
import sys

from olympus.routing.omniroute_adapter import OmniRouteAdapter


DEFAULT_MODEL = "openrouter/openrouter/free"
DEFAULT_URL = "http://127.0.0.1:20128"


def main():
    parser = argparse.ArgumentParser(description="OLYMPUS micro-task runner")
    parser.add_argument("prompt")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    router = OmniRouteAdapter(
        base_url=DEFAULT_URL,
        timeout_seconds=args.timeout,
    )

    result = router.execute(args.model, args.prompt)

    print("SUCCESS:", result.success)
    print("MODEL:", result.actual_model or "")
    print("PROVIDER:", result.provider or "")
    print("LATENCY_MS:", result.latency_ms)
    print("STATUS:", getattr(result.status, "value", result.status or ""))
    print("ERROR:", result.error or "")
    print()
    print(result.output if result.success else "")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
