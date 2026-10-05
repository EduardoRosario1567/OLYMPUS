#!/usr/bin/env python3
import argparse
import os
import sys
import threading
import time

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.routing.omniroute_adapter import OmniRouteAdapter


class LiveExecutionMonitor:
    """Show one fixed-line activity indicator while a task is running."""

    def __init__(self):
        self._started = time.time()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.wait(1):
            elapsed = int(time.time() - self._started)
            sys.stderr.write(
                "\r\x1b[2K● OLYMPUS trabalhando... %02d:%02d"
                % (elapsed // 60, elapsed % 60)
            )
            sys.stderr.flush()

    def stop(self, status):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        elapsed = int(time.time() - self._started)
        sys.stderr.write(
            "\r\x1b[2K%s %s %02d:%02d\n"
            % ("✓ OLYMPUS", status, elapsed // 60, elapsed % 60)
        )
        sys.stderr.flush()

def _telemetry_factory(monitor):
    # The user-facing monitor is intentionally a single fixed line.
    # Detailed events remain available to logs/API consumers, but must not
    # create a scrolling execution timeline in the terminal UI.
    def telemetry(event):
        return None
    return telemetry


def main():
    parser = argparse.ArgumentParser(description="Run a targetless OLYMPUS development task")
    parser.add_argument("task", help="Natural-language development objective")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--url", default="http://127.0.0.1:20128")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-iterations", type=int, default=12)
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    monitor = LiveExecutionMonitor()
    monitor.start()
    try:
        router = OmniRouteAdapter(base_url=args.url, timeout_seconds=args.timeout)
        developer = AutonomousDeveloper(root, router, telemetry=_telemetry_factory(monitor))
        result = developer.run(args.task, max_iterations=args.max_iterations)
    except KeyboardInterrupt:
        monitor.stop("interrompido")
        return 130
    except Exception as exc:
        monitor.stop("falhou")
        print("ERROR:", exc)
        return 1

    monitor.stop("concluído" if result.success else result.status)
    print("\n=== OLYMPUS DEVELOPER REPORT ===")
    print("STATUS:", result.status.upper())
    print("MODELS:", ", ".join(result.models_attempted) or "none")
    print("ITERATIONS:", result.iterations)
    print("FILES READ:", ", ".join(result.files_read) or "none")
    print("FILES MODIFIED:", ", ".join(result.files_modified) or "none")
    print("TESTS:", ", ".join(result.tests_run) or "none")
    if result.error:
        print("ERROR:", result.error)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
