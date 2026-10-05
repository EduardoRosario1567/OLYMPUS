import argparse
import os
import sys

from olympus.agent.safe_edit import SafeEditError, apply_edit
from olympus.routing.omniroute_adapter import OmniRouteAdapter


MODEL = "openrouter/openrouter/free"
URL = "http://127.0.0.1:20128"


def parse_edit(payload):
    search_tag = "=== SEARCH ==="
    replace_tag = "=== REPLACE ==="
    end_tag = "=== END ==="

    if search_tag not in payload:
        raise SafeEditError("missing SEARCH block")
    if replace_tag not in payload:
        raise SafeEditError("missing REPLACE block")
    if end_tag not in payload:
        raise SafeEditError("missing END block")

    before, rest = payload.split(search_tag, 1)
    search, rest = rest.split(replace_tag, 1)
    replace, after = rest.split(end_tag, 1)

    if before.strip() or after.strip():
        raise SafeEditError("content outside edit block")

    search = search.strip("\n")
    replace = replace.strip("\n")

    if not search:
        raise SafeEditError("empty SEARCH block")

    return search, replace


def main():
    parser = argparse.ArgumentParser(
        description="OLYMPUS safe micro-edit runner"
    )
    parser.add_argument("task")
    parser.add_argument("--target", required=True)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    root = os.getcwd()

    target_path = os.path.join(root, args.target)

    if not os.path.isfile(target_path):
        print("STATUS: BLOCKED")
        print("ERROR: target not found")
        return 2

    source = open(
        target_path,
        encoding="utf-8"
    ).read()

    prompt = """
Perform ONE minimal edit.

TARGET FILE:
%s

TASK:
%s

CURRENT SOURCE:
%s

Return ONLY:

=== SEARCH ===
<exact existing text>
=== REPLACE ===
<replacement text>
=== END ===

RULES:
- smallest possible change
- SEARCH must occur exactly once
- no markdown
- no explanation
- do not rewrite unrelated code
""" % (args.target, args.task, source)

    router = OmniRouteAdapter(
        base_url=URL,
        timeout_seconds=args.timeout,
    )

    result = router.execute(MODEL, prompt)

    print("MODEL_SUCCESS:", result.success)
    print("LATENCY_MS:", result.latency_ms)

    if not result.success:
        print("STATUS: FAIL")
        print("ERROR:", result.error)
        return 1

    try:
        search, replace = parse_edit(result.output)

        applied = apply_edit(
            root=root,
            relative_path=args.target,
            search=search,
            replace=replace,
            allowed_paths=[args.target],
        )

    except SafeEditError as exc:
        print("STATUS: BLOCKED")
        print("ERROR:", exc)
        return 2

    print("FILE:", applied.file)
    print("REPLACEMENTS:", applied.replacements)
    print("STATUS: PASS")

    return 0


if __name__ == "__main__":
    sys.exit(main())
