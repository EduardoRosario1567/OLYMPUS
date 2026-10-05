from app.core import provider_runtime as runtime
from olympus.routing.provider_fabric import GeminiNativeAdapter, ProviderConfig


def _adapter():
    return GeminiNativeAdapter(ProviderConfig(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gem_test_key",
        timeout_seconds=5,
    ))


def _catalog():
    return {
        "models": [
            {
                "name": "models/gemini-3.8-flash",
                "baseModelId": "gemini-3.8-flash",
                "supportedGenerationMethods": ["generateContent", "countTokens"],
                "inputTokenLimit": 1048576,
                "outputTokenLimit": 8192,
                "thinking": True,
            },
            {
                "name": "models/gemini-3.8-flash-tts",
                "baseModelId": "gemini-3.8-flash-tts",
                "supportedGenerationMethods": ["generateContent"],
                "outputTokenLimit": 2048,
            },
            {
                "name": "models/text-embedding-004",
                "baseModelId": "text-embedding-004",
                "supportedGenerationMethods": ["embedContent"],
            },
            {
                "name": "models/gemini-3.5-flash",
                "baseModelId": "gemini-3.5-flash",
                "supportedGenerationMethods": ["generateContent"],
                "outputTokenLimit": 4096,
            },
        ]
    }


def test_gemini_native_normalizes_legacy_openai_url_and_auth_header():
    adapter = _adapter()
    assert adapter.config.base_url == "https://generativelanguage.googleapis.com/v1beta"
    headers = adapter._headers()
    assert headers["x-goog-api-key"] == "gem_test_key"
    assert "Authorization" not in headers


def test_gemini_native_filters_catalog_by_generate_content_and_text_agent_safety(monkeypatch):
    adapter = _adapter()
    monkeypatch.setattr(adapter, "_request", lambda *a, **k: (200, _catalog()))
    models = adapter.list_models()
    assert [row.model_id for row in models] == ["gemini-3.8-flash", "gemini-3.5-flash"]
    assert models[0].metadata["output_token_limit"] == 8192
    assert "generateContent" in models[0].metadata["supported_generation_methods"]
    health = adapter.health()
    assert health.healthy is True
    assert health.metadata["models_count"] == 2
    assert health.metadata["catalog_total"] == 4


def test_gemini_native_generate_content_payload_and_text_parse(monkeypatch):
    adapter = _adapter()
    adapter._limits["gemini-3.8-flash"] = 8192
    seen = {}
    def request(method, path, payload=None, timeout=None):
        seen.update(method=method, path=path, payload=payload)
        return 200, {
            "modelVersion": "gemini-3.8-flash-001",
            "candidates": [{"content": {"parts": [
                {"thought": True, "text": "internal"},
                {"text": '{"type":"finish","target":null,"payload":null,"reason":"ok"}'},
            ]}}],
            "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 20},
        }
    monkeypatch.setattr(adapter, "_request", request)
    result = adapter.execute("gemini-3.8-flash", "return json", max_tokens=12000, temperature=0.0)
    assert result.success is True
    assert result.actual_model == "gemini-3.8-flash-001"
    assert '"type":"finish"' in result.output
    assert seen["path"] == "/models/gemini-3.8-flash:generateContent"
    cfg = seen["payload"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["maxOutputTokens"] == 8192
    assert cfg["temperature"] == 0.0


def test_gemini_native_rate_limit_is_capacity_signal(monkeypatch):
    adapter = _adapter()
    monkeypatch.setattr(adapter, "_request", lambda *a, **k: (429, {
        "error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota exceeded"}
    }))
    result = adapter.execute("gemini-3.8-flash", "hello", max_tokens=128)
    assert result.success is False
    assert result.status == "rate_limited"
    assert "RESOURCE_EXHAUSTED" in result.error


def test_registry_uses_gemini_native_adapter(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.delenv("OLYMPUS_GEMINI_URL", raising=False)
    registry = runtime.build_provider_registry(timeout_seconds=5)
    adapter = registry.adapter("gemini")
    assert isinstance(adapter, GeminiNativeAdapter)
    assert adapter.config.base_url == "https://generativelanguage.googleapis.com/v1beta"


def test_live_model_ranking_prefers_current_gemini_flash_families():
    ranked = runtime._rank_live_models((
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
    ))
    assert ranked[:4] == (
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
    )
