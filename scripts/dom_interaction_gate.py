#!/usr/bin/env python3
"""Browserless DOM contract gate for deterministic static web interactions.

This is not a replacement for a real browser. It is a deterministic safety
gate used when a browser binary is unavailable: it validates the common,
dependency-free interaction contract emitted by OLYMPUS static web missions.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class DOMParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.text = {}

    def handle_starttag(self, tag, attrs):
        attrs = {str(k).lower(): str(v or "") for k, v in attrs}
        node = {"tag": tag.lower(), "attrs": attrs}
        self.nodes.append(node)
        node_id = attrs.get("id")
        if node_id:
            self.text.setdefault(node_id, "")
        self.stack.append(node_id)

    def handle_endtag(self, _tag):
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1]:
            self.text[self.stack[-1]] = self.text.get(self.stack[-1], "") + data


def simulate(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    parser = DOMParser()
    parser.feed(source)
    button = next((node for node in parser.nodes if node["tag"] == "button" and node["attrs"].get("id")), None)
    if not button:
        raise RuntimeError("DOM gate: no identified button found")
    button_id = button["attrs"]["id"]
    onclick = button["attrs"].get("onclick", "")
    if not onclick:
        raise RuntimeError("DOM gate: button has no inline click contract")

    # Interpret the safe, dependency-free mutations produced by the OLYMPUS
    # action contract. Arbitrary JavaScript is deliberately not executed.
    mutations = re.findall(
        r"(?:this|document\.getElementById\(['\"]([^'\"]+)['\"]\))\.text(?:Content|contentText)\s*=\s*['\"]([^'\"]+)['\"]",
        onclick,
    )
    if not mutations:
        raise RuntimeError("DOM gate: click handler has no supported text mutation")

    simulated = dict(parser.text)
    for target, value in mutations:
        target = target or button_id
        simulated[target] = value

    expected = "Botão funcionando"
    if expected not in simulated.values():
        raise RuntimeError("DOM gate: expected click result was not produced")
    return {
        "button_id": button_id,
        "event": "click",
        "result": expected,
        "status": simulated.get("status", ""),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: dom_interaction_gate.py <html-file>", file=sys.stderr)
        return 2
    result = simulate(Path(sys.argv[1]).resolve())
    print(json.dumps({"gate_status": "PASS", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
