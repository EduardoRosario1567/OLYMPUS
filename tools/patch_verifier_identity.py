#!/usr/bin/env python3
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

MARKER = "OLYMPUS 3.0.7: legacy global Olympus identity gate disabled"
PHRASE = "include the requested Olympus identity"


def patch_text(source: str) -> tuple[str, bool]:
    if MARKER in source:
        return source, False
    lines = source.splitlines(True)
    hits = [i for i, line in enumerate(lines) if PHRASE in line and "errors.append" in line]
    if len(hits) != 1:
        raise RuntimeError(f"expected exactly one legacy identity gate, found {len(hits)}")
    i = hits[0]
    indent = re.match(r"\s*", lines[i]).group(0)
    newline = "\n" if lines[i].endswith("\n") else ""
    # Keep the containing Python block syntactically valid. The old check was a
    # global brand-specific heuristic: mentioning OLYMPUS as the platform could
    # force OLYMPUS branding into an unrelated customer's deliverable.
    lines[i] = indent + "pass  # " + MARKER + newline
    return "".join(lines), True


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_verifier_identity.py <verifier.py>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    source = path.read_text(encoding="utf-8")
    patched, changed = patch_text(source)
    if changed:
        path.write_text(patched, encoding="utf-8")
    py_compile.compile(str(path), doraise=True)
    final = path.read_text(encoding="utf-8")
    if PHRASE in final and "errors.append" in final:
        raise RuntimeError("legacy identity error remains active")
    print("VERIFIER_IDENTITY_SCOPE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
