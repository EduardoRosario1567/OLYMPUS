#!/usr/bin/env python3
import argparse
import os
import sys

from olympus.agent.mission import AutonomousPatchRunner, load_mission
from olympus.routing.omniroute_adapter import OmniRouteAdapter


def _telemetry(event):
    kind = event.get("event", "event").upper()
    step = event.get("step")
    prefix = "[OLYMPUS]"
    if step:
        prefix += " STEP %s" % step
    details = []
    for key in ("model", "status", "iterations", "error"):
        value = event.get(key)
        if value not in (None, "", []):
            details.append("%s=%s" % (key, value))
    print("%s %s%s" % (prefix, kind, (" " + " ".join(details)) if details else ""), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Run an OLYMPUS autonomous patch mission")
    parser.add_argument("mission", help="Path to PATCH mission markdown")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--url", default="http://127.0.0.1:20128")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    mission = load_mission(args.mission)
    router = OmniRouteAdapter(base_url=args.url, timeout_seconds=args.timeout)
    runner = AutonomousPatchRunner(args.root, router, telemetry=_telemetry)
    result = runner.run(mission)

    print("\n=== OLYMPUS MISSION REPORT ===")
    print("MISSION:", result.mission.id)
    print("STATUS:", result.status.upper())
    print("STEPS:", "%d/%d" % (len(result.steps), len(result.mission.steps)))
    for item in result.steps:
        print(
            "%s | %s | model=%s | iterations=%d | files=%s | tests=%s"
            % (
                item.step.id,
                item.loop_result.state.status.value,
                "%s%s" % (item.model, (" [attempted: %s]" % ",".join(item.models_attempted)) if len(item.models_attempted) > 1 else ""),
                item.loop_result.state.iteration,
                ",".join(item.loop_result.state.files_modified) or "none",
                ",".join(item.loop_result.state.tests_run) or "none",
            )
        )
    if result.error:
        print("ERROR:", result.error)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
