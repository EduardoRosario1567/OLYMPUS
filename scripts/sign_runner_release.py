#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from olympus.distribution import create_signed_release


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign one already verified Olympus Runner bundle.")
    parser.add_argument("artifact")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--minimum-version", required=True)
    parser.add_argument("--channel", choices=("stable", "beta"), default="stable")
    parser.add_argument("--platform", choices=("linux", "macos", "windows"), required=True)
    parser.add_argument("--architecture", choices=("x86_64", "arm64"), required=True)
    parser.add_argument("--artifact-url", required=True)
    arguments = parser.parse_args()
    manifest = create_signed_release(
        arguments.artifact, arguments.manifest, arguments.signature,
        private_key=arguments.private_key, public_key=arguments.public_key,
        version=arguments.version, minimum_version=arguments.minimum_version,
        channel=arguments.channel, platform=arguments.platform,
        architecture=arguments.architecture, artifact_url=arguments.artifact_url,
    )
    print(json.dumps(manifest.payload(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
