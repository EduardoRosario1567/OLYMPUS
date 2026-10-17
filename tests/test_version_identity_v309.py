import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "frontend/public/olympus-version.json"


def test_product_version_has_one_source_of_truth():
    identity = json.loads(
        VERSION_FILE.read_text(encoding="utf-8")
    )

    assert identity["product"] == "olympus"
    assert identity["version"]
    assert identity["build"]

    backend = (
        ROOT / "backend/app/main.py"
    ).read_text(encoding="utf-8")

    sidebar = (
        ROOT / "frontend/components/layout/sidebar.tsx"
    ).read_text(encoding="utf-8")

    mission = (
        ROOT / "frontend/app/missao/page.tsx"
    ).read_text(encoding="utf-8")

    sharing = (
        ROOT / "frontend/components/technical-share-tools.tsx"
    ).read_text(encoding="utf-8")

    launcher = (
        ROOT / "start_olympus.command"
    ).read_text(encoding="utf-8")

    assert "olympus-version.json" in backend
    assert 'APP_VERSION = "' not in backend
    assert 'APP_BUILD = "' not in backend

    assert '@/public/olympus-version.json' in sidebar
    assert '@/public/olympus-version.json' in mission
    assert '@/public/olympus-version.json' in sharing

    assert "frontend/public/olympus-version.json" in launcher

    literal = re.compile(
        r"OLYMPUS\s+\d+\.\d+\.\d+"
    )

    assert not literal.search(sidebar)
    assert not literal.search(mission)
    assert not literal.search(sharing)


def test_launcher_checks_both_runtime_sides():
    launcher = (
        ROOT / "start_olympus.command"
    ).read_text(encoding="utf-8")

    assert "backend_current" in launcher
    assert "frontend_current" in launcher
    assert "EXPECTED_VERSION" in launcher
    assert "wait_current backend_current" in launcher
    assert "wait_current frontend_current" in launcher
