import json
from pathlib import Path

from backend.app.core import provider_runtime as pr
from olympus.agent.control_plane import AgentControlPlane
from olympus.agent.model_selector import OlympusModelSelector


def test_pool_status_routes_are_ordered_before_legacy(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "_REPO_ROOT", tmp_path)
    status = tmp_path / ".olympus/runtime/omniroute-pools.json"
    status.parent.mkdir(parents=True)
    status.write_text(json.dumps({
        "primary_combo": "Conding-free",
        "primary_combo_ready": True,
        "ollama_local_ready": ["ollama/qwen2.5-coder:7b"],
        "ollama_cloud_ready": ["ollamacloud/qwen3-coder:480b-cloud"],
        "expanded_combo": "Conding-free-max",
        "expanded_combo_ready": True,
    }))
    routes = pr._omniroute_tier_routes(990000)
    assert [r.id for r in routes] == [
        "Conding-free",
        "ollama/qwen2.5-coder:7b",
        "ollamacloud/qwen3-coder:480b-cloud",
        "Conding-free-max",
    ]
    assert [r.provider for r in routes] == ["conding_free", "ollama_local", "ollama_cloud", "conding_free_expanded"]


def test_pool_status_fails_closed_when_optional_tiers_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "_REPO_ROOT", tmp_path)
    routes = pr._omniroute_tier_routes(990000)
    assert [r.id for r in routes] == ["Conding-free"]
    assert [r.provider for r in routes] == ["conding_free"]


def test_control_plane_uses_route_metadata_for_failure_domains():
    routes = (
        pr.AgentModelRoute("Conding-free", "free", "conding_free", 1000),
        pr.AgentModelRoute("ollama/qwen", "local", "ollama_local", 990),
        pr.AgentModelRoute("ollamacloud/qwen", "cloud", "ollama_cloud", 980),
    )
    selector = OlympusModelSelector(routes)
    plane = AgentControlPlane(".", object(), selector, lambda *a: None, lambda *a: None)
    assert plane._provider_for("Conding-free") == "conding_free"
    assert plane._provider_for("ollama/qwen") == "ollama_local"
    assert plane._provider_for("ollamacloud/qwen") == "ollama_cloud"
