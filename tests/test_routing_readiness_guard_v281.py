import json
import time
from pathlib import Path
from unittest.mock import patch

from olympus.routing.interfaces import RoutingModelInfo, ModelCapability
from olympus.routing.provider_fabric import ProviderRegistry


def _model(model_id, provider="openrouter"):
    return RoutingModelInfo(model_id, provider, [ModelCapability.CODIGO], True)


class Omni:
    def __init__(self, models):
        self.models = models
    def list_models(self):
        return list(self.models)


class DeadOllama:
    def list_models(self):
        raise OSError("connection refused")


class LiveOllama:
    def list_models(self):
        return [_model("qwen2.5-coder:7b", "ollama")]


def _write_pool(root: Path, **overrides):
    path = root / ".olympus/runtime/omniroute-pools.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": time.time(),
        "primary_combo": "Conding-free",
        "ollama_local_ready": [],
        "ollama_cloud_ready": [],
        "expanded_combo": None,
        "expanded_combo_ready": False,
        "openrouter_new_probe_ready": [],
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_unreachable_local_ollama_is_not_a_candidate(tmp_path, monkeypatch):
    from app.core import provider_runtime as pr
    monkeypatch.setattr(pr, "_REPO_ROOT", tmp_path)
    _write_pool(tmp_path)
    reg = ProviderRegistry()
    reg.register("omniroute", Omni([_model("openrouter/google/gemma-4-26b-a4b-it:free")]), 10)
    reg.register("ollama", DeadOllama(), 20)
    with patch.dict("os.environ", {
        "OLYMPUS_FREE_FALLBACK_PROVIDERS": "openrouter,ollama",
    }, clear=False):
        ids = tuple(r.id for r in pr.configured_mission_routes(reg, {"free_attempt_limit": 3}))
    assert not any(i.startswith("ollama::") for i in ids)
    assert ids[0] == "Conding-free"


def test_live_local_ollama_can_join_candidates(tmp_path, monkeypatch):
    from app.core import provider_runtime as pr
    monkeypatch.setattr(pr, "_REPO_ROOT", tmp_path)
    _write_pool(tmp_path)
    reg = ProviderRegistry()
    reg.register("omniroute", Omni([]), 10)
    reg.register("ollama", LiveOllama(), 20)
    with patch.dict("os.environ", {
        "OLYMPUS_FREE_FALLBACK_PROVIDERS": "ollama",
    }, clear=False):
        ids = tuple(r.id for r in pr.configured_mission_routes(reg, {"free_attempt_limit": 3}))
    assert "ollama::qwen2.5-coder:7b" in ids


def test_recent_verified_openrouter_models_are_prioritized(tmp_path, monkeypatch):
    from app.core import provider_runtime as pr
    monkeypatch.setattr(pr, "_REPO_ROOT", tmp_path)
    verified = "openrouter/google/gemma-4-26b-a4b-it:free"
    _write_pool(tmp_path, openrouter_new_probe_ready=[verified])
    reg = ProviderRegistry()
    reg.register("omniroute", Omni([
        _model("openrouter/cohere/north-mini-code:free"),
        _model(verified),
        _model("openrouter/google/gemma-4-31b-it:free"),
    ]), 10)
    with patch.dict("os.environ", {"OLYMPUS_FREE_FALLBACK_PROVIDERS": ""}, clear=False):
        ids = tuple(r.id for r in pr.configured_mission_routes(reg, {"free_attempt_limit": 3}))
    assert ids[:3] == ("Conding-free", verified, "openrouter/cohere/north-mini-code:free")


def test_stale_pool_does_not_advertise_optional_tiers(tmp_path, monkeypatch):
    from app.core import provider_runtime as pr
    monkeypatch.setattr(pr, "_REPO_ROOT", tmp_path)
    _write_pool(
        tmp_path,
        updated_at=time.time() - 999999,
        ollama_local_ready=["ollama/qwen2.5-coder:7b"],
        ollama_cloud_ready=["ollama-cloud/qwen3.5:397b"],
        expanded_combo="shadow",
        expanded_combo_ready=True,
    )
    with patch.dict("os.environ", {"OLYMPUS_OMNIROUTE_POOL_MAX_AGE_SECONDS": "60"}, clear=False):
        routes = pr._omniroute_tier_routes(1000)
    assert [r.id for r in routes] == ["Conding-free"]
