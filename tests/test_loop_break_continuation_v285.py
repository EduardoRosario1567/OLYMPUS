from types import SimpleNamespace
from backend.app.api import cloud_runtime as api


def test_segue_is_control_not_new_software_task(monkeypatch):
    assert api._is_continuation_task("SEGUE")
    assert api._is_continuation_task("  retomar! ")
    assert not api._is_continuation_task("crie uma landing page")


def test_continuation_skips_cancelled_control_mission(monkeypatch):
    rows = [
        SimpleNamespace(status="cancelled", task="SEGUE", execution_id="control"),
        SimpleNamespace(status="paused_capacity", task="Crie uma landing page", execution_id="landing"),
    ]
    class FakeRuntime:
        def list(self, tenant_id, limit, project_id=None, status=None):
            return rows
    monkeypatch.setattr(api, "_RUNTIME", FakeRuntime())
    chosen = api._latest_meaningful_resumable("p1", "local")
    assert chosen.execution_id == "landing"
