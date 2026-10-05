#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from olympus.distribution import verify_signed_release


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an Olympus Runner release before publishing it.")
    parser.add_argument("artifact")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--current-version")
    parser.add_argument("--channel", choices=("stable", "beta"), default="stable")
    parser.add_argument("--platform", choices=("linux", "macos", "windows"), required=True)
    parser.add_argument("--architecture", choices=("x86_64", "arm64"), required=True)
    arguments = parser.parse_args()
    verified = verify_signed_release(
        arguments.manifest, arguments.signature, arguments.artifact,
        public_key=arguments.public_key, expected_platform=arguments.platform,
        expected_architecture=arguments.architecture, expected_channel=arguments.channel,
        current_version=arguments.current_version,
    )
    print(json.dumps(verified.release.payload(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
