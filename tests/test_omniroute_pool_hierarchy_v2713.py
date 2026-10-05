import json
from pathlib import Path
from backend.app.core import provider_runtime as pr


def test_primary_order_remains_conding_then_ollamas(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, '_REPO_ROOT', tmp_path)
    p=tmp_path/'.olympus/runtime/omniroute-pools.json'; p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
      'primary_combo':'Conding-free','primary_combo_ready':True,
      'ollama_local_ready':['ollama/qwen:7b'],
      'ollama_cloud_ready':['ollamacloud/qwen3-coder']
    }))
    routes=pr._omniroute_tier_routes(990000)
    assert [r.id for r in routes][:3] == ['Conding-free','ollama/qwen:7b','ollamacloud/qwen3-coder']


def test_missing_discovery_never_removes_conding(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, '_REPO_ROOT', tmp_path)
    routes=pr._omniroute_tier_routes(990000)
    assert routes[0].id == 'Conding-free'
