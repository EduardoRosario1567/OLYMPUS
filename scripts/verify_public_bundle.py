#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from olympus.distribution import BundlePolicyError, verify_public_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an OLYMPUS public Runner bundle")
    parser.add_argument("archive", help="ZIP archive to verify")
    args = parser.parse_args()
    try:
        manifest = verify_public_bundle(args.archive)
    except BundlePolicyError as exc:
        print("BLOCKED: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(manifest.payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
