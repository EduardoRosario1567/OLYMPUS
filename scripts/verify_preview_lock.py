#!/usr/bin/env python3
"""Validate the reviewed preview npm lock without installing or running packages."""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def verify(package_path, lock_path):
    package = json.loads(Path(package_path).read_text())
    raw = Path(lock_path).read_bytes()
    lock = json.loads(raw)
    if lock.get("lockfileVersion") != 3:
        raise ValueError("npm lockfile version 3 required")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise ValueError("lock packages missing")
    root = packages.get("")
    if not isinstance(root, dict):
        raise ValueError("lock root missing")
    for field in ("name", "version", "dependencies"):
        if lock.get(field) != package.get(field) and field != "dependencies":
            raise ValueError("lock identity mismatch: " + field)
        if root.get(field) != package.get(field):
            raise ValueError("lock root mismatch: " + field)
    for name, record in packages.items():
        if not name:
            continue
        parts = name.split("/")
        if not name.startswith("node_modules/") or ".." in parts or "." in parts or "\\" in name:
            raise ValueError("unsafe dependency path")
        if not isinstance(record, dict) or record.get("link"):
            raise ValueError("linked dependency refused")
        url = urlsplit(str(record.get("resolved", "")))
        if (url.scheme != "https" or url.hostname != "registry.npmjs.org"
                or url.username or url.password or url.query or url.fragment
                or url.port not in (None, 443)):
            raise ValueError("non-registry dependency refused")
        integrity = record.get("integrity", "")
        if not re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", integrity):
            raise ValueError("SHA-512 package integrity required")
        if len(base64.b64decode(integrity[7:], validate=True)) != 64:
            raise ValueError("invalid SHA-512 package integrity")
        if not isinstance(record.get("version"), str) or not record["version"]:
            raise ValueError("exact resolved version missing")
    for name, requested in package["dependencies"].items():
        installed = packages.get("node_modules/" + name, {}).get("version")
        matches = installed == requested
        if requested.startswith("~"):
            minimum = requested[1:].split(".")
            resolved = str(installed).split(".")
            matches = (len(minimum) == len(resolved) == 3
                       and all(x.isdigit() for x in minimum + resolved)
                       and minimum[:2] == resolved[:2]
                       and int(resolved[2]) >= int(minimum[2]))
        if not matches:
            raise ValueError("direct dependency mismatch: " + name)
    return {"status": "PASS", "package_count": len(packages)-1,
            "lock_sha256": hashlib.sha256(raw).hexdigest(),
            "direct_dependencies": {name: packages["node_modules/"+name]["version"]
                                    for name in package["dependencies"]}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package")
    parser.add_argument("lock")
    args = parser.parse_args()
    print(json.dumps(verify(args.package, args.lock), sort_keys=True))


if __name__ == "__main__":
    main()
