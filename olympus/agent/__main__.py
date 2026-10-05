import argparse
import os
import sys

from olympus.agent.model_selector import OlympusModelSelector
from olympus.agent.orchestrator import OlympusAgent
from olympus.routing.omniroute_adapter import OmniRouteAdapter


DEFAULT_URL = "http://127.0.0.1:20128"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="olympus-agent",
        description="OLYMPUS DEV AGENT V1",
    )

    parser.add_argument("task")

    parser.add_argument(
        "--target",
        required=True,
        help="Single target file the agent may generate",
    )

    parser.add_argument(
        "--test",
        action="append",
        required=False,
        dest="tests",
        help="Optional tests.* unittest module",
    )

    args = parser.parse_args()

    root = os.getcwd()

    router = OmniRouteAdapter(
        base_url=DEFAULT_URL,
        api_key=(os.environ.get("OLYMPUS_OMNIROUTE_API_KEY") or os.environ.get("OMNIROUTE_API_KEY") or None),
        timeout_seconds=30,
    )

    selector = OlympusModelSelector()
    selected_model = selector.select(args.task)

    tests = list(args.tests or [])

    if not tests:
        from olympus.agent.test_generator import AcceptanceTestGenerator
        from olympus.agent.test_resolver import resolve_test_module

        try:
            resolved_test = resolve_test_module(
                root,
                args.target,
            )
        except ValueError:
            resolved_test = None

        generic_fallbacks = {
            "tests.test_safe_apply",
        }

        if (
            resolved_test is None
            or resolved_test in generic_fallbacks
        ):
            print("TEST: generating acceptance test")

            generator = AcceptanceTestGenerator(
                router=router,
                model_id=selected_model,
                root=root,
            )

            tests = [
                generator.generate(
                    task=args.task,
                    target=args.target,
                )
            ]
        else:
            tests = [resolved_test]

        print("TEST SELECTED:", tests[0])

    print("MODEL SELECTED:", selected_model)

    models = [
        "openrouter/openrouter/free",
    ]

    ordered_models = [selected_model] + [
        model for model in models
        if model != selected_model
    ]

    result = None

    for attempt, model_id in enumerate(ordered_models, 1):
        print(
            "MODEL ATTEMPT %d/%d: %s"
            % (attempt, len(ordered_models), model_id)
        )

        agent = OlympusAgent(
            router=router,
            model_id=model_id,
            root=root,
        )

        result = agent.run(
            task=args.task,
            target=args.target,
            allowed_paths=[args.target],
            test_modules=tests,
        )

        if result.success:
            break

        status = (result.execution_status or "").lower()
        error_text = (result.error or "").lower()

        technical_failure = (
            status in {
                "timeout",
                "provider_error",
                "rate_limited",
                "unavailable",
                "authentication_error",
            }
            or "timeout" in error_text
            or "timed out" in error_text
            or "connection" in error_text
        )

        if not technical_failure:
            break

        print(
            "TECHNICAL FAILURE: %s"
            % (result.execution_status or result.error or "unknown")
        )

        if attempt < len(ordered_models):
            print("FALLBACK: trying next Olympus candidate")

    print()
    print("=== OLYMPUS DEV AGENT ===")
    print("TASK:", result.task)
    print("MODEL:", result.actual_model or result.requested_model)
    print("PROVIDER:", result.provider or "")
    print("FILES:", ", ".join(result.files_modified) or "none")
    print("TESTS:", ", ".join(result.tests_run) or "none")
    print("TESTS_PASS:", result.tests_passed)
    print("LATENCY_MS:", result.latency_ms)
    print("STATUS:", "PASS" if result.success else "FAIL")

    if result.error:
        print("ERROR:", result.error)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
