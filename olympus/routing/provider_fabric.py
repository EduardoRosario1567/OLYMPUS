"""Provider-agnostic AI Fabric for OLYMPUS.

Keeps provider health/routing separate from model identity.  The first generic
adapter targets OpenAI-compatible HTTP APIs, which covers several cloud and
local gateways without coupling the agent runtime to any one vendor.
"""
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, Optional, Tuple
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from olympus.routing.interfaces import (
    ModelCapability, RoutingExecutionResult, RoutingHealth, RoutingModelInfo,
)
from olympus.routing.image_inputs import validated_image_inputs, image_message


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    base_url: str
    api_key: Optional[str] = None
    enabled: bool = True
    kind: str = "openai_compatible"
    default_headers: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    wire_api: str = "chat_completions"
    catalog_url: Optional[str] = None


class OpenAICompatibleAdapter:
    """Minimal adapter for OpenAI-compatible /models + /chat/completions APIs."""
    def __init__(self, config: ProviderConfig):
        self.config = config

    def _headers(self):
        # Some provider edge protections reject Python's default urllib user
        # agent with HTTP 403 before the API key is even evaluated. Identify
        # the product explicitly while keeping the client provider-neutral.
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OLYMPUS/2.6.2",
        }
        headers.update(self.config.default_headers)
        if self.config.api_key:
            headers["Authorization"] = "Bearer %s" % self.config.api_key
        return headers

    def _request_url(self, method, url, payload=None, timeout=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urlopen(req, timeout=timeout or self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return exc.code, {"error": body or str(exc)}

    def _request(self, method, path, payload=None, timeout=None):
        return self._request_url(
            method,
            self.config.base_url.rstrip("/") + path,
            payload=payload,
            timeout=timeout,
        )

    def health(self):
        if not self.config.enabled:
            return RoutingHealth(False, self.config.provider_id, "disabled")
        try:
            status, data = self._request("GET", "/models", timeout=2)
            healthy = 200 <= status < 400
            model_ids = tuple(
                str(item.get("id")) for item in data.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ) if isinstance(data, dict) else ()
            return RoutingHealth(healthy, self.config.provider_id,
                                 "healthy" if status < 400 else "degraded",
                                 {"http_status": status, "kind": self.config.kind,
                                  "models_count": len(model_ids), "models": model_ids[:500]})
        except (URLError, OSError, ValueError) as exc:
            return RoutingHealth(False, self.config.provider_id, "unreachable",
                                 {"error": str(exc), "kind": self.config.kind})

    def list_models(self):
        status, data = self._request("GET", "/models")
        if status >= 400:
            return []
        result = []
        for item in data.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            result.append(RoutingModelInfo(
                model_id=model_id, provider=self.config.provider_id,
                capabilities=[ModelCapability.TEXTO, ModelCapability.CODIGO] + (
                    [ModelCapability.IMAGEM] if 'image' in (item.get('architecture') or {}).get('input_modalities', []) else []),
                available=True, metadata={"raw": item},
            ))
        return result

    @staticmethod
    def _failed_tool_action(data):
        """Recover the safe action a compatible API embedded in an HTTP 400."""
        value = data.get("error") if isinstance(data, dict) else data
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                return ""
        if isinstance(value, dict) and isinstance(value.get("error"), dict):
            value = value["error"]
        failed = value.get("failed_generation") if isinstance(value, dict) else None
        if isinstance(failed, dict):
            return json.dumps(failed, ensure_ascii=False)
        if isinstance(failed, str) and failed.strip().startswith("{"):
            try:
                decoded = json.loads(failed)
            except (TypeError, ValueError):
                return ""
            return json.dumps(decoded, ensure_ascii=False) if isinstance(decoded, dict) else ""
        return ""

    @staticmethod
    def _responses_output(data):
        direct = data.get("output_text") if isinstance(data, dict) else None
        if isinstance(direct, str) and direct.strip():
            return direct
        texts = []
        for item in data.get("output", []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call" and item.get("name"):
                arguments = item.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (TypeError, ValueError):
                        arguments = {}
                return json.dumps({"name": item["name"], "arguments": arguments}, ensure_ascii=False)
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
        return "\n".join(texts)

    def execute(self, model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
        try:
            images = validated_image_inputs(kwargs.get('image_inputs'))
        except ValueError:
            return RoutingExecutionResult(model_id, '', self.config.provider_id, '', 0, 0.0,
                                          False, 'invalid inline image input', {}, 'invalid_image_input')
        responses_api = self.config.wire_api == "responses"
        payload = (
            {"model": model_id, "input": image_message(prompt, images, responses=True)}
            if responses_api else
            {"model": model_id, "messages": [{"role": "user", "content": image_message(prompt, images)}]}
        )
        token_key = "max_output_tokens" if responses_api else "max_tokens"
        if max_tokens is not None:
            payload[token_key] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        started = time.monotonic()
        try:
            retry_count = 0
            token_budget_repaired = False
            while True:
                status, data = self._request("POST", "/responses" if responses_api else "/chat/completions", payload)
                error_text = str(data.get("error", ""))
                retry_match = re.search(
                    r"try again in\s+([0-9]+(?:\.[0-9]+)?)(ms|s)",
                    error_text,
                    flags=re.IGNORECASE,
                )
                # Groq's free token budget is provider-wide. Immediately
                # hopping to another Groq model consumes the same exhausted
                # bucket, so honor its short reset window before failover.
                if status == 429 and retry_match and retry_count < 4:
                    delay_value = float(retry_match.group(1))
                    if retry_match.group(2).lower() == "ms":
                        delay_value /= 1000.0
                    delay = min(30.0, max(0.25, delay_value + 0.25))
                    time.sleep(delay)
                    retry_count += 1
                    continue
                max_tokens_match = (
                    re.search(
                        r"max(?:_output)?_tokens.*?less than or equal to [`']?([0-9]{2,6})",
                        error_text,
                        flags=re.IGNORECASE,
                    )
                    or re.search(
                        r"maximum value for [`']?max(?:_output)?_tokens[`']?.*?([0-9]{2,6})",
                        error_text,
                        flags=re.IGNORECASE,
                    )
                )
                if status == 400 and max_tokens_match and not token_budget_repaired:
                    allowed = int(max_tokens_match.group(1))
                    requested = int(payload.get(token_key, allowed))
                    payload[token_key] = min(requested, allowed)
                    token_budget_repaired = True
                    continue
                break
            latency = max(1, int((time.monotonic() - started) * 1000))
            if status >= 400:
                error = str(data.get("error", "provider error"))
                normalized_error = error.lower()
                if status == 429:
                    execution_status = "rate_limited"
                elif status in (401, 403):
                    execution_status = "authentication_error"
                elif status == 402:
                    execution_status = "billing_error"
                elif status == 404:
                    execution_status = "unavailable"
                elif status >= 500:
                    execution_status = "provider_error"
                elif status == 400 and any(token in normalized_error for token in (
                    "tool_use_failed",
                    "tool choice is none",
                    "failed_generation",
                )):
                    # Some OpenAI-compatible models may emit an internal tool
                    # call even though Olympus requested a plain JSON action.
                    # This is a model/protocol mismatch, not a logical mission
                    # failure, so the control plane must try the next model.
                    recovered_action = self._failed_tool_action(data)
                    if recovered_action:
                        return RoutingExecutionResult(
                            model_id, model_id, self.config.provider_id,
                            recovered_action, latency, 0.0, True, None,
                            {
                                "http_status": status,
                            "rate_limit_retries": retry_count,
                            "token_budget_repaired": token_budget_repaired,
                                "protocol_recovered": "failed_tool_generation",
                            },
                            "success",
                        )
                    execution_status = "malformed_response"
                elif status == 400 and any(token in normalized_error for token in (
                    "model_decommissioned",
                    "model_not_found",
                    "model not found",
                    "does not exist",
                    "not permitted to use",
                )):
                    execution_status = "unavailable"
                else:
                    execution_status = "unknown_error"
                return RoutingExecutionResult(model_id, "", self.config.provider_id, "", latency, 0.0,
                                              False, error,
                                              {"http_status": status, "rate_limit_retries": retry_count,
                                               "token_budget_repaired": token_budget_repaired}, execution_status)
            choices = data.get("choices") or []
            output = self._responses_output(data) if responses_api else ""
            if not responses_api and choices:
                message = choices[0].get("message") or {}
                output = message.get("content") or ""
                if not str(output).strip():
                    tool_calls = message.get("tool_calls") or []
                    first = tool_calls[0] if tool_calls else None
                    function = first.get("function", first) if isinstance(first, dict) else None
                    if isinstance(function, dict) and function.get("name"):
                        output = json.dumps(function, ensure_ascii=False)
            if not output.strip():
                return RoutingExecutionResult(
                    model_id, data.get("model", model_id), self.config.provider_id,
                    "", latency, 0.0, False,
                    "model returned no textual action",
                    {"http_status": status, "usage": data.get("usage"), "rate_limit_retries": retry_count,
                     "token_budget_repaired": token_budget_repaired},
                    "malformed_response",
                )
            return RoutingExecutionResult(model_id, data.get("model", model_id), self.config.provider_id,
                                          output, latency, 0.0, True, None,
                                          {"http_status": status, "usage": data.get("usage"), "rate_limit_retries": retry_count,
                                           "token_budget_repaired": token_budget_repaired,
                                           "image_inputs_sent": len(images),
                                           "actual_model_reported": isinstance(data.get('model'),str) and bool(data['model'].strip())}, "success")
        except Exception as exc:
            latency = max(1, int((time.monotonic() - started) * 1000))
            return RoutingExecutionResult(model_id, "", self.config.provider_id, "", latency, 0.0,
                                          False, str(exc), {"error_class": type(exc).__name__}, "technical_failure")


class GeminiNativeAdapter(OpenAICompatibleAdapter):
    """Gemini-native adapter for catalog-aware, agent-safe qualification.

    Google exposes an OpenAI-compatible beta surface, but the native Gemini
    API exposes the facts Olympus actually needs for safe routing: whether a
    model supports ``generateContent`` and its input/output token limits.
    This adapter therefore uses ``/v1beta/models`` for discovery and
    ``models/{model}:generateContent`` for inference while preserving the
    generic RoutingAdapter contract used by Capacity Fabric.
    """

    _BLOCKED_MODEL_TOKENS = (
        "embedding", "embed-", "imagen", "veo", "tts", "speech", "audio",
        "live", "aqa", "robotics", "computer-use", "image-generation",
        "-image", "vision-preview-image",
    )

    def __init__(self, config: ProviderConfig):
        # Accept an old /openai configuration and normalize it to the native
        # v1beta root. Existing installations therefore do not need a new key
        # or manual URL migration.
        base = str(config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        if base.endswith("/openai"):
            base = base[:-len("/openai")]
        super().__init__(ProviderConfig(
            config.provider_id,
            base,
            config.api_key,
            enabled=config.enabled,
            kind="gemini_native",
            default_headers=config.default_headers,
            timeout_seconds=config.timeout_seconds,
            wire_api="gemini_generate_content",
            catalog_url=config.catalog_url,
        ))
        self._limits = {}

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OLYMPUS/3.0.3",
        }
        headers.update(self.config.default_headers)
        if self.config.api_key:
            headers["x-goog-api-key"] = self.config.api_key
        return headers

    @staticmethod
    def _error_text(data):
        if not isinstance(data, dict):
            return str(data or "provider error")
        value = data.get("error", data)
        if isinstance(value, dict):
            message = str(value.get("message") or value.get("status") or value)
            status = str(value.get("status") or "").strip()
            return (status + ": " + message).strip(": ") if status else message
        return str(value or "provider error")

    @classmethod
    def _usable_model(cls, item):
        if not isinstance(item, dict):
            return False
        methods = tuple(str(x) for x in (item.get("supportedGenerationMethods") or ()))
        if "generateContent" not in methods:
            return False
        raw_name = str(item.get("baseModelId") or item.get("name") or "").strip()
        name = raw_name.rsplit("/", 1)[-1].lower()
        if not name or not name.startswith("gemini-"):
            return False
        return not any(token in name for token in cls._BLOCKED_MODEL_TOKENS)

    @staticmethod
    def _model_id(item):
        value = str(item.get("baseModelId") or item.get("name") or "").strip()
        return value.rsplit("/", 1)[-1]

    def _catalog(self, timeout=None):
        return self._request("GET", "/models?pageSize=1000", timeout=timeout)

    def _catalog_models(self, timeout=None):
        status, data = self._catalog(timeout=timeout)
        rows = data.get("models", []) if isinstance(data, dict) else []
        usable = tuple(item for item in rows if self._usable_model(item))
        return status, data, usable

    def health(self):
        if not self.config.enabled:
            return RoutingHealth(False, self.config.provider_id, "disabled")
        try:
            status, data, rows = self._catalog_models(timeout=3)
            model_ids = tuple(self._model_id(item) for item in rows if self._model_id(item))
            healthy = 200 <= status < 400
            return RoutingHealth(
                healthy,
                self.config.provider_id,
                "healthy" if healthy else "degraded",
                {
                    "http_status": status,
                    "kind": "gemini_native",
                    "models_count": len(model_ids),
                    "models": model_ids[:500],
                    "catalog_total": len(data.get("models", [])) if isinstance(data, dict) else 0,
                    "generation_filter": "supportedGenerationMethods:generateContent",
                    "error": None if healthy else self._error_text(data),
                },
            )
        except (URLError, OSError, ValueError) as exc:
            return RoutingHealth(
                False, self.config.provider_id, "unreachable",
                {"error": str(exc), "kind": "gemini_native"},
            )

    def list_models(self):
        status, data, rows = self._catalog_models()
        if status >= 400:
            return []
        result = []
        for item in rows:
            model_id = self._model_id(item)
            if not model_id:
                continue
            try:
                output_limit = int(item.get("outputTokenLimit") or 0)
            except (TypeError, ValueError):
                output_limit = 0
            try:
                input_limit = int(item.get("inputTokenLimit") or 0)
            except (TypeError, ValueError):
                input_limit = 0
            if output_limit > 0:
                self._limits[model_id] = output_limit
            capabilities = [ModelCapability.TEXTO, ModelCapability.CODIGO]
            if bool(item.get("thinking")):
                capabilities.append(ModelCapability.ARQUITETURA)
            result.append(RoutingModelInfo(
                model_id=model_id,
                provider=self.config.provider_id,
                capabilities=capabilities,
                available=True,
                metadata={
                    "raw": item,
                    "input_token_limit": input_limit,
                    "output_token_limit": output_limit,
                    "supported_generation_methods": tuple(item.get("supportedGenerationMethods") or ()),
                    "native_api": True,
                },
            ))
        return result

    @staticmethod
    def _extract_text(data):
        primary = []
        fallback = []
        for candidate in data.get("candidates", []) if isinstance(data, dict) else []:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            parts = content.get("parts", []) if isinstance(content, dict) else []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                fallback.append(text)
                if not part.get("thought"):
                    primary.append(text)
        return "\n".join(primary or fallback).strip()

    def execute(self, model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
        model = str(model_id or "").strip().rsplit("/", 1)[-1]
        generation = {"responseMimeType": "application/json"}
        if max_tokens is not None:
            requested = max(1, int(max_tokens))
            known_limit = int(self._limits.get(model) or 0)
            generation["maxOutputTokens"] = min(requested, known_limit) if known_limit > 0 else requested
        if temperature is not None:
            generation["temperature"] = float(temperature)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": str(prompt)}]}],
            "generationConfig": generation,
        }
        started = time.monotonic()
        try:
            status, data = self._request("POST", "/models/%s:generateContent" % model, payload)
            latency = max(1, int((time.monotonic() - started) * 1000))
            if status >= 400:
                error = self._error_text(data)
                normalized = error.lower()
                if status == 429 or "resource_exhausted" in normalized or "quota" in normalized:
                    execution_status = "rate_limited"
                elif status in (401, 403) and not any(token in normalized for token in ("quota", "billing")):
                    execution_status = "authentication_error"
                elif status == 402 or "billing" in normalized:
                    execution_status = "billing_error"
                elif status == 404 or "not found" in normalized or "not supported" in normalized:
                    execution_status = "unavailable"
                elif status >= 500:
                    execution_status = "provider_error"
                else:
                    execution_status = "unknown_error"
                return RoutingExecutionResult(
                    model_id, "", self.config.provider_id, "", latency, 0.0,
                    False, error, {"http_status": status, "native_api": True}, execution_status,
                )
            output = self._extract_text(data)
            if not output:
                finish_reasons = [
                    str(item.get("finishReason") or "")
                    for item in data.get("candidates", []) if isinstance(item, dict)
                ] if isinstance(data, dict) else []
                return RoutingExecutionResult(
                    model_id, str(data.get("modelVersion") or model), self.config.provider_id,
                    "", latency, 0.0, False,
                    "gemini returned no textual action",
                    {"http_status": status, "native_api": True, "finish_reasons": finish_reasons,
                     "usage": data.get("usageMetadata") if isinstance(data, dict) else None},
                    "malformed_response",
                )
            return RoutingExecutionResult(
                model_id, str(data.get("modelVersion") or model), self.config.provider_id,
                output, latency, 0.0, True, None,
                {"http_status": status, "native_api": True,
                 "usage": data.get("usageMetadata") if isinstance(data, dict) else None},
                "success",
            )
        except Exception as exc:
            latency = max(1, int((time.monotonic() - started) * 1000))
            return RoutingExecutionResult(
                model_id, "", self.config.provider_id, "", latency, 0.0,
                False, str(exc), {"error_class": type(exc).__name__, "native_api": True},
                "technical_failure",
            )


class CloudflareWorkersAIAdapter(OpenAICompatibleAdapter):
    """Workers AI adapter with Cloudflare-native model discovery.

    Chat generation uses Cloudflare's OpenAI-compatible ``/ai/v1`` endpoint,
    while model discovery lives at ``/ai/models/search``.  Keeping those two
    surfaces explicit avoids pretending Workers AI exposes ``/v1/models``.
    """

    @staticmethod
    def _catalog_rows(data):
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        for key in ("data", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = value.get("data")
                if isinstance(nested, list):
                    return nested
        return []

    @staticmethod
    def _model_id(item):
        if not isinstance(item, dict):
            return ""
        for key in ("id", "name", "model", "slug"):
            value = str(item.get(key) or "").strip()
            if value.startswith("@cf/") or value.startswith("@hf/"):
                return value
        for key in ("id", "name", "model", "slug"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return ""

    def _catalog(self, timeout=None):
        if not self.config.catalog_url:
            return 0, {"error": "cloudflare catalog url missing"}
        query = urlencode({"format": "openrouter", "hide_experimental": "true", "per_page": 100})
        separator = "&" if "?" in self.config.catalog_url else "?"
        return self._request_url(
            "GET", self.config.catalog_url + separator + query, timeout=timeout
        )

    def health(self):
        if not self.config.enabled:
            return RoutingHealth(False, self.config.provider_id, "disabled")
        try:
            status, data = self._catalog(timeout=3)
            rows = self._catalog_rows(data)
            models = tuple(filter(None, (self._model_id(item) for item in rows)))
            healthy = 200 <= status < 400
            return RoutingHealth(
                healthy, self.config.provider_id,
                "healthy" if healthy else "degraded",
                {
                    "http_status": status,
                    "kind": "cloudflare_workers_ai",
                    "models_count": len(models),
                    "models": models[:500],
                },
            )
        except (URLError, OSError, ValueError) as exc:
            return RoutingHealth(
                False, self.config.provider_id, "unreachable",
                {"error": str(exc), "kind": "cloudflare_workers_ai"},
            )

    def list_models(self):
        status, data = self._catalog()
        if status >= 400:
            return []
        result = []
        for item in self._catalog_rows(data):
            model_id = self._model_id(item)
            if not model_id:
                continue
            task = str(item.get("task") or item.get("pipeline_tag") or "").lower() if isinstance(item, dict) else ""
            if task:
                if any(token in task for token in ("image", "audio", "speech", "embedding", "classification", "translation")):
                    continue
                if not any(token in task for token in ("text-generation", "text_generation", "chat", "completion", "llm")):
                    continue
            result.append(RoutingModelInfo(
                model_id=model_id, provider=self.config.provider_id,
                capabilities=[ModelCapability.TEXTO, ModelCapability.CODIGO],
                available=True, metadata={"raw": item},
            ))
        return result


class ProviderRegistry:
    """Registry and health-aware provider selector. No provider is mandatory."""
    def __init__(self):
        self._providers = {}

    def register(self, provider_id, adapter, priority=100):
        self._providers[provider_id] = (priority, adapter)
        return adapter

    def ids(self):
        return tuple(k for k, _ in sorted(self._providers.items(), key=lambda x: x[1][0]))

    def adapter(self, provider_id):
        return self._providers[provider_id][1]

    def health_all(self):
        provider_ids = self.ids()

        def check(provider_id):
            adapter = self.adapter(provider_id)
            try:
                return adapter.health()
            except Exception as exc:
                return RoutingHealth(False, provider_id, "unreachable", {"error": str(exc)})

        if len(provider_ids) < 2:
            return tuple(check(provider_id) for provider_id in provider_ids)
        with ThreadPoolExecutor(max_workers=min(8, len(provider_ids))) as pool:
            # executor.map preserves registry priority order while avoiding one
            # provider timeout delaying every status card behind it.
            return tuple(pool.map(check, provider_ids))

    def healthy_ids(self):
        return tuple(h.provider for h in self.health_all() if h.healthy)

    def ranked_routes(self, model_id=None):
        routes = []
        for provider_id in self.healthy_ids():
            adapter = self.adapter(provider_id)
            if model_id is None:
                routes.append((provider_id, None))
                continue
            try:
                models = {m.model_id for m in adapter.list_models() if m.available}
            except Exception:
                models = set()
            if model_id in models:
                routes.append((provider_id, model_id))
        return tuple(routes)


ROUTE_SEPARATOR = "::"


def provider_route_id(provider_id: str, model_id: str) -> str:
    """Encode a provider and model without confusing either identity.

    Model slugs frequently contain ``/`` themselves, therefore a dedicated
    separator is used instead of trying to infer the provider from the slug.
    """
    provider = str(provider_id or "").strip()
    model = str(model_id or "").strip()
    if not provider or not model or ROUTE_SEPARATOR in provider:
        raise ValueError("provider and model are required")
    return "%s%s%s" % (provider, ROUTE_SEPARATOR, model)


def split_provider_route(route_id: str, default_provider: str) -> Tuple[str, str]:
    value = str(route_id or "").strip()
    if ROUTE_SEPARATOR not in value:
        return default_provider, value
    provider, model = value.split(ROUTE_SEPARATOR, 1)
    if not provider or not model:
        raise ValueError("invalid provider route")
    return provider, model


class MultiProviderRoutingAdapter:
    """Route one agent contract across independent provider adapters.

    Unqualified model IDs remain backward compatible and go through the
    default provider (normally OmniRoute). Qualified IDs use
    ``provider::model`` and are never sent to the wrong adapter.
    """

    def __init__(self, registry: ProviderRegistry, default_provider: str = "omniroute"):
        if default_provider not in registry.ids():
            raise ValueError("default provider is not registered")
        self.registry = registry
        self.default_provider = default_provider

    def _route(self, route_id: str):
        provider_id, model_id = split_provider_route(route_id, self.default_provider)
        try:
            adapter = self.registry.adapter(provider_id)
        except KeyError:
            raise ValueError("unknown provider route: %s" % provider_id)
        return provider_id, model_id, adapter

    def health(self):
        rows = self.registry.health_all()
        healthy = tuple(row.provider for row in rows if row.healthy)
        return RoutingHealth(
            bool(healthy),
            "multi-provider",
            "healthy" if healthy else "unreachable",
            {"healthy_providers": healthy, "providers": self.registry.ids()},
        )

    def list_models(self):
        models = []
        for provider_id in self.registry.ids():
            adapter = self.registry.adapter(provider_id)
            try:
                provider_models = adapter.list_models()
            except Exception:
                continue
            for item in provider_models:
                route_id = (
                    item.model_id
                    if provider_id == self.default_provider
                    else provider_route_id(provider_id, item.model_id)
                )
                metadata = dict(item.metadata)
                metadata.update({"provider_model_id": item.model_id, "route_provider": provider_id})
                models.append(RoutingModelInfo(
                    route_id,
                    provider_id,
                    list(item.capabilities),
                    item.available,
                    metadata,
                ))
        return models

    def execute(self, model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
        provider_id, provider_model_id, adapter = self._route(model_id)
        result = adapter.execute(
            provider_model_id,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        metadata = dict(result.metadata)
        metadata.update({"route_provider": provider_id, "provider_model_id": provider_model_id})
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model=result.actual_model,
            provider=provider_id,
            output=result.output,
            latency_ms=result.latency_ms,
            cost=result.cost,
            success=result.success,
            error=result.error,
            metadata=metadata,
            status=result.status,
        )
