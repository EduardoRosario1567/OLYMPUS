from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_start_always_restarts_frontend_and_clears_next():
    text = read("start_olympus.command")
    assert 'safe_stop_port 3000 "$ROOT/frontend"' in text
    assert 'rm -rf "$ROOT/frontend/.next"' in text
    assert 'npm run dev -- --hostname 127.0.0.1 --port 3000' in text
    assert 'wait_current frontend_current 90' in text


def test_start_sanitizes_known_transient_backend_override():
    text = read("start_olympus.command")
    assert 'env -u OLYMPUS_OMNIROUTE_URL' in text


def test_start_refuses_to_kill_unknown_port_owner():
    text = read("start_olympus.command")
    assert 'CWD=$cwd' in text
    assert '[ "$cwd" = "$expected_cwd" ]' in text
    assert 'pertence a outro processo' in text


def test_installer_requires_real_browser_hydration_gate():
    from tests.frontend_contract import check_browser
    check_browser('hydration')


def test_version_is_306_everywhere_relevant():
    import json
    from app.main import app
    from fastapi.testclient import TestClient
    metadata = json.loads((ROOT / "frontend/public/olympus-version.json").read_text())
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert app.version == metadata["version"]
    assert response.json()["version"] == metadata["version"]
    assert response.json()["build"] == metadata["build"]
