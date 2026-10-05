#!/usr/bin/env python3
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DIRS = ("olympus", "tests", "scripts", "docs", "contexts")
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "requirements-core.txt",
    "olympus/agent/loop.py",
    "olympus/agent/mission.py",
    "olympus/agent/control_plane.py",
    "olympus/agent/actions.py",
    "olympus/routing/provider_fabric.py",
    "backend/app/core/provider_runtime.py",
    "configure_ai.command",
    "scripts/configure_ai_providers.py",
    "scripts/investor_landing_smoke.py",
    "tests/test_investor_landing_smoke_v221.py",
    "tests/test_provider_failover_v210.py",
    "tests/test_reliability_gate_v250.py",
    "tests/test_design_offer_skills_v251.py",
    "tests/test_agent_ecosystem_v260.py",
    "olympus/skills/builtin/offer-engineering.skill.json",
    "olympus/skills/builtin/emil-design-eng.skill.json",
    "olympus/skills/builtin/ui-ux-pro-max.skill.json",
    "olympus/skills/builtin/web-design-guidelines.skill.json",
    "olympus/skills/builtin/brandkit.skill.json",
    "olympus/skills/builtin/extract-design-system.skill.json",
    "olympus/skills/builtin/image-to-code.skill.json",
    "olympus/skills/builtin/systematic-delivery.skill.json",
    "olympus/skills/builtin/product-sprint.skill.json",
    "olympus/skills/builtin/spec-driven-development.skill.json",
    "olympus/skills/builtin/context-efficiency.skill.json",
    "olympus/skills/builtin/checkpoint-continuity.skill.json",
    "olympus/skills/builtin/social-media-strategy.skill.json",
    "olympus/skills/builtin/exposure-audit.skill.json",
    "olympus/skills/builtin/answer-first.skill.json",
    "olympus/agent/patch_engine.py",
    "olympus/agent/repo_map.py",
    "tests/test_agent_runtime_v2.py",
    "tests/test_autonomous_mission.py",
    "olympus/cloud/secret_vault.py",
    "olympus/cloud/railway_provider.py",
    "olympus/distribution/runner_access.py",
    "olympus/distribution/signed_updates.py",
    "scripts/sign_runner_release.py",
    "scripts/verify_runner_release.py",
    "tests/test_kms_secret_vault.py",
    "tests/test_signed_runner_updates.py",
    "olympus/saas/platform.py",
    "olympus/saas/billing.py",
    "backend/app/api/saas.py",
    "frontend/app/configuracoes/page.tsx",
    "frontend/app/convite/page.tsx",
    "tests/test_saas_platform.py",
)

sys.path.insert(0, str(ROOT))

missing = []
for rel in REQUIRED_DIRS:
    if not (ROOT / rel).is_dir():
        missing.append(rel + "/")
for rel in REQUIRED_FILES:
    if not (ROOT / rel).is_file():
        missing.append(rel)

if missing:
    print("INSTALLATION: FAIL")
    for item in missing:
        print("MISSING:", item)
    raise SystemExit(1)

importlib.import_module("olympus")
importlib.import_module("olympus.agent.loop")
importlib.import_module("olympus.agent.mission")
importlib.import_module("olympus.agent.control_plane")
importlib.import_module("olympus.saas.platform")

print("INSTALLATION: PASS")
print("ROOT:", ROOT)
print("DIRECTORY CONTRACT: PASS")
print("PYTHON IMPORTS: PASS")
