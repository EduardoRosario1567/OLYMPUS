import importlib.util
from pathlib import Path


def _load_sync():
    path = Path(__file__).resolve().parents[1] / "scripts" / "omniroute_pool_sync.py"
    spec = importlib.util.spec_from_file_location("pool_sync_v2717", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_ollama_cloud_prefix_and_provider_are_classified():
    sync = _load_sync()
    assert sync._classify_ollama({"id": "ollama-cloud/qwen3.5:397b"}) == "cloud"
    assert sync._classify_ollama({"id": "x", "provider": "ollama-cloud"}) == "cloud"
    assert sync._classify_ollama({"id": "x", "providerId": "ollamacloud"}) == "cloud"


def test_catalog_payload_variants_are_normalized():
    sync = _load_sync()
    rows = sync._rows_from_payload({"models": ["ollama-cloud/glm-5.1", {"modelId": "ollama-cloud/kimi-k2.6"}]})
    assert [r["id"] for r in rows] == ["ollama-cloud/glm-5.1", "ollama-cloud/kimi-k2.6"]


def test_ready_cloud_model_enters_omniroute_tier_route(tmp_path, monkeypatch):
    import json
    import app.core.provider_runtime as runtime

    monkeypatch.setattr(runtime, "_REPO_ROOT", tmp_path)
    status_path = tmp_path / ".olympus" / "runtime" / "omniroute-pools.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(json.dumps({
        "primary_combo": "Conding-free",
        "ollama_local_ready": [],
        "ollama_cloud_ready": ["ollama-cloud/qwen3.5:397b"],
    }), encoding="utf-8")
    routes = runtime._omniroute_tier_routes(1000)
    assert routes[0].id == "Conding-free"
    assert any(r.provider == "ollama_cloud" and r.id == "ollama-cloud/qwen3.5:397b" for r in routes)
