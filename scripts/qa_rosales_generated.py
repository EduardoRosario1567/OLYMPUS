"""Deterministic, read-only quality gate for generated Rosales Café pilot.
No NPM, remote calls, AI inference or app execution. Fails closed.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "entregas" / "rosales-cafe-real-pilot"
APP = ROOT / "app"
RESULT = ROOT / "quality-report.json"

def run():
    source = "\n".join(p.read_text(encoding="utf-8") for p in sorted((APP / "src").rglob("*.jsx")))
    ids = set(re.findall(r'\bid=["\']([A-Za-z][\w-]*)["\']', source))
    anchors = set(re.findall(r'\bhref=["\']#([A-Za-z][\w-]*)["\']', source))
    failures = []
    for value in sorted(anchors - ids):
        failures.append({"id": "broken_internal_anchor", "detail": "#"+value})
    unverifiable = [
        (r"\bfundad[oa]\b", "foundation_history_not_confirmed"),
        (r"\bsustentabilidad[ea]\b", "sustainability_claim_not_confirmed"),
        (r"\bdesde a seleção\b", "sourcing_claim_not_confirmed"),
    ]
    for regex, tag in unverifiable:
        if re.search(regex, source, re.I):
            failures.append({"id": "unverified_marketing_fact", "detail": tag})
    if not re.search(r"Rosales Café", source):
        failures.append({"id": "missing_brand", "detail": "brand not found"})
    if not (APP/"package.json").is_file() or not (APP/"index.html").is_file():
        failures.append({"id": "missing_runtime_files", "detail": "Vite project incomplete"})
    result = {"status": "BLOCKED" if failures else "STATIC_CHECKS_PASSED",
              "browser_review": "pending", "checks": {"anchors":len(anchors),"ids":len(ids)},
              "findings":failures}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return bool(failures)

if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
