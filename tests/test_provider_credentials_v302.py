import os
from pathlib import Path

from app.core import provider_runtime as runtime
from olympus.routing.provider_fabric import CloudflareWorkersAIAdapter, ProviderConfig


def _isolated_credentials(tmp_path, monkeypatch):
    path = tmp_path / "backend.env"
    path.write_text("# test\n", encoding="utf-8")
    monkeypatch.setenv("OLYMPUS_CREDENTIALS_PATH", str(path))
    for key in ("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    return path


def test_cloudflare_requires_two_fields_and_never_exposes_values(tmp_path, monkeypatch):
    path = _isolated_credentials(tmp_path, monkeypatch)
    fields = runtime.provider_credential_fields("cloudflare")
    assert [row["id"] for row in fields] == ["api_token", "account_id"]
    assert all(row["configured"] is False for row in fields)

    runtime.update_provider_credentials("cloudflare", {
        "api_token": "cf_secret_token",
        "account_id": "abcDEF_123456",
    })
    text = path.read_text(encoding="utf-8")
    assert "CLOUDFLARE_API_KEY=cf_secret_token" in text
    assert "CLOUDFLARE_ACCOUNT_ID=abcDEF_123456" in text
    public = runtime.provider_credential_fields("cloudflare")
    assert all(row["configured"] for row in public)
    assert "cf_secret_token" not in repr(public)
    assert "abcDEF_123456" not in repr(public)


def test_cloudflare_registry_builds_account_scoped_urls(tmp_path, monkeypatch):
    _isolated_credentials(tmp_path, monkeypatch)
    runtime.update_provider_credentials("cloudflare", {
        "api_token": "token",
        "account_id": "account123456",
    })
    registry = runtime.build_provider_registry(timeout_seconds=5)
    adapter = registry.adapter("cloudflare")
    assert isinstance(adapter, CloudflareWorkersAIAdapter)
    assert adapter.config.base_url == "https://api.cloudflare.com/client/v4/accounts/account123456/ai/v1"
    assert adapter.config.catalog_url == "https://api.cloudflare.com/client/v4/accounts/account123456/ai/models/search"
    assert adapter.config.enabled is True


def test_partial_update_preserves_existing_cloudflare_field(tmp_path, monkeypatch):
    path = _isolated_credentials(tmp_path, monkeypatch)
    runtime.update_provider_credentials("cloudflare", {"api_token": "first", "account_id": "account123456"})
    runtime.update_provider_credentials("cloudflare", {"api_token": "second"})
    text = path.read_text(encoding="utf-8")
    assert "CLOUDFLARE_API_KEY=second" in text
    assert "CLOUDFLARE_ACCOUNT_ID=account123456" in text


def test_backward_single_key_provider_still_works(tmp_path, monkeypatch):
    path = _isolated_credentials(tmp_path, monkeypatch)
    runtime.update_provider_secret("groq", "gsk_test")
    assert os.environ["GROQ_API_KEY"] == "gsk_test"
    assert "GROQ_API_KEY=gsk_test" in path.read_text(encoding="utf-8")


def test_remove_cloudflare_clears_full_credential_set(tmp_path, monkeypatch):
    path = _isolated_credentials(tmp_path, monkeypatch)
    runtime.update_provider_credentials("cloudflare", {"api_token": "token", "account_id": "account123456"})
    runtime.remove_provider_credentials("cloudflare")
    text = path.read_text(encoding="utf-8")
    assert "CLOUDFLARE_API_KEY=" not in text
    assert "CLOUDFLARE_ACCOUNT_ID=" not in text
    assert "CLOUDFLARE_API_KEY" not in os.environ
    assert "CLOUDFLARE_ACCOUNT_ID" not in os.environ


def test_cloudflare_adapter_parses_openrouter_catalog_shape(monkeypatch):
    adapter = CloudflareWorkersAIAdapter(ProviderConfig(
        "cloudflare",
        "https://api.cloudflare.com/client/v4/accounts/account123456/ai/v1",
        "token",
        catalog_url="https://api.cloudflare.com/client/v4/accounts/account123456/ai/models/search",
    ))
    monkeypatch.setattr(adapter, "_request_url", lambda *a, **k: (200, {"data": [
        {"id": "@cf/openai/gpt-oss-20b", "task": "text-generation"},
        {"id": "@cf/example/image", "task": "text-to-image"},
    ]}))
    models = adapter.list_models()
    assert [row.model_id for row in models] == ["@cf/openai/gpt-oss-20b"]
    health = adapter.health()
    assert health.healthy is True
    assert health.metadata["models_count"] == 2
