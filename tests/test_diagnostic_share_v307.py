from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_share_controls_work_after_history_navigation():
    from tests.frontend_contract import check_browser
    check_browser('diagnostic')


def test_secret_redaction_contract_is_present():
    helper = (ROOT / "frontend/lib/diagnostic-share.ts").read_text(encoding="utf-8")
    for token in ("Bearer", "API[_-]?KEY", "TOKEN", "SECRET", "PASSWORD", "authorization", "cookie"):
        assert token in helper
    assert "[REDACTED]" in helper
