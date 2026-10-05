"""
OmniRouteAdapter — Concrete implementation of RoutingAdapter for OmniRoute.

Este adapter conecta o Olympus ao OmniRoute via HTTP (OpenAI-compatible API).
Não acopla o Olympus Core ao OmniRoute — apenas implementa o protocolo
RoutingAdapter definido em olympus.routing.interfaces.
"""

import json
import re
import socket
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
    ModelCapability,
)

from olympus.models import ExecutionStatus


def _elapsed_ms(start: float) -> int:
    """Return elapsed time in whole milliseconds, with a 1 ms floor.

    Monotonic timers can legitimately yield sub-millisecond durations in
    local/fake transports; the public metric contract represents durations
    in integer milliseconds, so zero is reserved for values that were never
    measured rather than completed executions.
    """
    return max(1, int((time.perf_counter() - start) * 1000))


def _decode_response_body(raw: str) -> dict:
    """Decode JSON or normalize an OpenAI-compatible SSE response.

    OmniRoute may stream even when the client explicitly sends
    ``"stream": false``.  Normalizing the chunks here keeps that transport
    quirk outside the provider-independent runtime.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as original_error:
        content_parts = []
        reasoning_parts = []
        response_id = None
        created = 0
        model = ""
        role = "assistant"
        finish_reason = None
        usage = None
        saw_event = False
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            payload = stripped[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            saw_event = True
            response_id = event.get("id") or response_id
            created = event.get("created") or created
            model = event.get("model") or model
            usage = event.get("usage") or usage
            choices = event.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            if isinstance(delta, dict):
                role = delta.get("role") or role
                if isinstance(delta.get("content"), str):
                    content_parts.append(delta["content"])
                if isinstance(delta.get("reasoning_content"), str):
                    reasoning_parts.append(delta["reasoning_content"])
            finish_reason = choice.get("finish_reason") or finish_reason
        if not saw_event:
            raise original_error
        message = {"role": role, "content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        return {
            "id": response_id or "chatcmpl-omniroute-sse",
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": usage,
        }


def classify_execution_error(
    http_status: Optional[int] = None,
    error_type: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> ExecutionStatus:
    """Classifica erro de execução HTTP em ExecutionStatus determinístico (PATCH 004C).

    Entrada: HTTP status + error_type + error_code + mensagem/metadata.
    Saída: ExecutionStatus enum value.

    Mapeamento determinístico:
    - timeout/network timeout → timeout
    - 401/403 authentication → authentication_error
    - 402/payment/billing → billing_error
    - 429/rate limit → rate_limited
    - provider unavailable/circuit breaker → unavailable
    - 5xx/provider failure → provider_error
    - JSON/parse failure → malformed_response
    - outros → unknown_error

    Se houver ambiguidade: unknown_error.
    """
    # Timeout de rede / timeout local
    if metadata and metadata.get("error_class") in ("TimeoutError", "timeout"):
        return ExecutionStatus.TIMEOUT

    # HTTP status codes
    if http_status is not None:
        # 401/403 - Authentication
        if http_status in (401, 403):
            return ExecutionStatus.AUTHENTICATION_ERROR

        # 402 - Billing/Payment required
        if http_status == 402:
            return ExecutionStatus.BILLING_ERROR

        # 429 - Rate limited
        if http_status == 429:
            return ExecutionStatus.RATE_LIMITED

        # 5xx - Provider error
        if 500 <= http_status < 600:
            return ExecutionStatus.PROVIDER_ERROR

        # 404 - Could be unavailable model
        if http_status == 404:
            return ExecutionStatus.UNAVAILABLE

    # error_type / error_code strings
    if error_type:
        et = error_type.lower()
        if "timeout" in et:
            return ExecutionStatus.TIMEOUT
        if "rate" in et and "limit" in et:
            return ExecutionStatus.RATE_LIMITED
        if "auth" in et or "unauthorized" in et or "forbidden" in et:
            return ExecutionStatus.AUTHENTICATION_ERROR
        if "billing" in et or "payment" in et or "quota" in et:
            return ExecutionStatus.BILLING_ERROR
        if "unavailable" in et or "circuit" in et or "overload" in et:
            return ExecutionStatus.UNAVAILABLE
        if "provider" in et or "upstream" in et:
            return ExecutionStatus.PROVIDER_ERROR

    if error_code:
        ec = error_code.lower()
        if "timeout" in ec:
            return ExecutionStatus.TIMEOUT
        if "rate_limit" in ec or "ratelimit" in ec:
            return ExecutionStatus.RATE_LIMITED
        if "auth" in ec or "unauthorized" in ec or "forbidden" in ec:
            return ExecutionStatus.AUTHENTICATION_ERROR
        if "billing" in ec or "payment" in ec or "quota" in ec:
            return ExecutionStatus.BILLING_ERROR
        if "unavailable" in ec or "circuit" in ec:
            return ExecutionStatus.UNAVAILABLE

    # Malformed response - empty choices, parse failure
    if error_message:
        em = error_message.lower()
        if "json" in em or "parse" in em or "decode" in em:
            return ExecutionStatus.MALFORMED_RESPONSE
        if "empty choices" in em:
            return ExecutionStatus.MALFORMED_RESPONSE

    # Metadata diagnostics for circuit breaker / unavailable
    if metadata:
        diag = metadata.get("diagnostics")
        if diag:
            diag_str = str(diag).lower()
            if "circuit" in diag_str or "unavailable" in diag_str:
                return ExecutionStatus.UNAVAILABLE

    # Default
    return ExecutionStatus.UNKNOWN_ERROR


def _max_tokens_limit_from_response(data: object) -> Optional[int]:
    """Extract a provider-reported output-token ceiling from an error body.

    OmniRoute forwards several providers with slightly different wording.  A
    rejected ``max_tokens`` value is a request-shape problem, not a reason to
    abandon the whole mission or immediately burn a fallback route.  Keep the
    parser deliberately conservative: only messages that mention the token
    field and a limit/maximum are eligible for one bounded retry.
    """
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if isinstance(error, dict):
        fragments = [error.get("message"), error.get("detail"), str(error)]
    else:
        fragments = [error, data.get("message"), str(data)]
    text = " ".join(str(item or "") for item in fragments).strip()
    folded = text.lower()
    if "max_tokens" not in folded and "max_output_tokens" not in folded:
        return None
    if not any(token in folded for token in ("maximum", "max value", "limit", "less than or equal", "at most", "<=", "context")):
        return None
    patterns = (
        r"(?:less than or equal to|at most|<=)\s*[`']?([0-9]{2,6})",
        r"(?:maximum|max(?:imum)? value|limit)[^0-9]{0,40}([0-9]{2,6})",
        r"max(?:_output)?_tokens[^0-9]{0,120}([0-9]{2,6})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


class OmniRouteAdapter:
    """
    Adapter para o OmniRoute via HTTP.

    Implementa RoutingAdapter usando apenas a standard library (urllib).
    Sem dependências externas, sem subprocess, sem arquivos internos do OmniRoute.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:20128",
        api_key: Optional[str] = None,
        timeout_seconds: float = 180.0,
    ) -> None:
        """
        Args:
            base_url: URL base do servidor OmniRoute (ex: http://127.0.0.1:20128)
            api_key: Chave de API opcional para autenticação Bearer
            timeout_seconds: Timeout para requisições HTTP
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _make_request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
    ) -> tuple[int, dict]:
        """
        Faz requisição HTTP e retorna (status_code, response_json).
        Lança URLError/HTTPError em falhas de rede/HTTP.
        """
        url = f"{self._base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(url, data=data, headers=headers, method=method)

        with urlopen(req, timeout=self._timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, _decode_response_body(raw)

    def _parse_capabilities(self, caps_raw: dict) -> list[ModelCapability]:
        """Converte capabilities raw do OmniRoute para ModelCapability enum."""
        capabilities = []
        # Mapeamento conhecido de capabilities do OmniRoute -> ModelCapability
        capability_map = {
            "tool_calling": ModelCapability.TESTES,  # proxy para tool use
            "reasoning": ModelCapability.ARQUITETURA,
            "thinking": ModelCapability.ARQUITETURA,
            "temperature": ModelCapability.TEXTO,
            "vision": ModelCapability.IMAGEM,
            "supportsThinking": ModelCapability.ARQUITETURA,
        }
        for key, value in caps_raw.items():
            if value and key in capability_map:
                capabilities.append(capability_map[key])
        # Deduplicar mantendo ordem
        seen = set()
        unique = []
        for c in capabilities:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def list_models(self) -> list[RoutingModelInfo]:
        """Lista modelos disponíveis no OmniRoute via GET /v1/models."""
        status, data = self._make_request("GET", "/v1/models")
        if status != 200:
            raise RuntimeError(f"OmniRoute list_models failed: HTTP {status}")

        models = []
        for item in data.get("data", []):
            caps_raw = item.get("capabilities", {})
            capabilities = self._parse_capabilities(caps_raw)

            model = RoutingModelInfo(
                model_id=item.get("id", ""),
                provider=item.get("owned_by", "unknown"),
                capabilities=capabilities,
                available=True,  # catálogo público = disponível
                metadata={
                    "context_length": item.get("context_length"),
                    "max_input_tokens": item.get("max_input_tokens"),
                    "max_output_tokens": item.get("max_output_tokens"),
                    "root": item.get("root"),
                    "owned_by": item.get("owned_by"),
                    "capabilities_raw": caps_raw,
                    "created": item.get("created"),
                    "object": item.get("object"),
                    "permission": item.get("permission"),
                    "parent": item.get("parent"),
                },
            )
            models.append(model)
        return models

    def health(self) -> RoutingHealth:
        """
        Verifica liveness do servidor OmniRoute usando GET /v1/models.

        NOTA: Isto é um liveness check, não provider health completo.
        O OmniRoute expõe provider health em /api/health mas requer
        management token que não assumimos disponível.
        """
        start = time.perf_counter()
        try:
            status, data = self._make_request("GET", "/v1/models")
            latency_ms = _elapsed_ms(start)
            if status == 200 and isinstance(data, dict) and "data" in data:
                return RoutingHealth(
                    healthy=True,
                    provider="omniroute",
                    status="liveness_ok",
                    metadata={
                        "check_type": "liveness",
                        "endpoint": "/v1/models",
                        "latency_ms": latency_ms,
                        "models_count": len(data.get("data", [])),
                        "models": tuple(
                            str(item.get("id")) for item in data.get("data", [])
                            if isinstance(item, dict) and item.get("id")
                        )[:50],
                    },
                )
            return RoutingHealth(
                healthy=False,
                provider="omniroute",
                status=f"unexpected_response_{status}",
                metadata={
                    "check_type": "liveness",
                    "endpoint": "/v1/models",
                    "latency_ms": latency_ms,
                    "status_code": status,
                },
            )
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as e:
            latency_ms = _elapsed_ms(start)
            return RoutingHealth(
                healthy=False,
                provider="omniroute",
                status="unreachable",
                metadata={
                    "check_type": "liveness",
                    "endpoint": "/v1/models",
                    "latency_ms": latency_ms,
                    "error": str(e),
                },
            )

    def execute(
        self,
        model_id: str,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> RoutingExecutionResult:
        """
        Executa prompt no modelo via POST /v1/chat/completions (non-stream).

        Args:
            model_id: ID do modelo (ex: "auto/coding", "openrouter/gpt-4o")
            prompt: Texto do prompt do usuário
            max_tokens: Limite opcional de tokens de saída
            temperature: Temperatura opcional de sampling
            **kwargs: Ignorados (reservados para extensão futura)

        Returns:
            RoutingExecutionResult com resultado tipado.
        """
        start = time.perf_counter()
        body = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature

        token_budget_repaired = False
        try:
            # Some providers behind OmniRoute enforce a smaller output ceiling
            # than the advertised model catalog.  Retry once with the exact
            # ceiling reported by the provider before handing off to another
            # model.  This keeps a request-shape mismatch from looking like a
            # model outage and preserves the mission's fallback budget.
            while True:
                try:
                    status, data = self._make_request("POST", "/v1/chat/completions", body)
                except HTTPError as e:
                    try:
                        raw = e.read().decode("utf-8")
                        data = json.loads(raw) if raw else {}
                    except (OSError, UnicodeDecodeError, ValueError, TypeError):
                        data = {}
                    if not isinstance(data, dict):
                        data = {"error": {"message": str(data)}}
                    status = e.code

                allowed_tokens = _max_tokens_limit_from_response(data)
                requested_tokens = body.get("max_tokens")
                if (
                    status == 400
                    and allowed_tokens is not None
                    and isinstance(requested_tokens, int)
                    and requested_tokens > allowed_tokens
                    and not token_budget_repaired
                ):
                    body["max_tokens"] = allowed_tokens
                    token_budget_repaired = True
                    continue
                break

            latency_ms = _elapsed_ms(start)

            # Sucesso HTTP 200
            if status == 200:
                choices = data.get("choices", [])
                if not choices:
                    error_msg = "Empty choices in response"
                    metadata = {
                        "raw_response": data,
                        "http_status": status,
                        "token_budget_repaired": token_budget_repaired,
                    }
                    execution_status = classify_execution_error(
                        http_status=status,
                        error_message=error_msg,
                        metadata=metadata,
                    )
                    return RoutingExecutionResult(
                        requested_model=model_id,
                        actual_model="",
                        provider="",
                        output="",
                        latency_ms=latency_ms,
                        cost=0.0,
                        success=False,
                        error=error_msg,
                        metadata=metadata,
                        status=execution_status.value,
                    )

                choice = choices[0]
                if not isinstance(choice, dict):
                    error_msg = "Malformed response: first choice is not an object"
                    metadata = {"raw_response": data, "http_status": status, "token_budget_repaired": token_budget_repaired}
                    return RoutingExecutionResult(
                        requested_model=model_id, actual_model="", provider="", output="",
                        latency_ms=latency_ms, cost=0.0, success=False, error=error_msg,
                        metadata=metadata, status=ExecutionStatus.MALFORMED_RESPONSE.value,
                    )
                message = choice.get("message") or {}
                if not isinstance(message, dict):
                    message = {}
                raw_output = message.get("content")
                output = raw_output if isinstance(raw_output, str) else ""
                if not output.strip():
                    # Some compatible providers return tool calls or reasoning while
                    # leaving content=null. Recover structured tool output when safe;
                    # otherwise fail closed instead of returning success with None.
                    tool_calls = message.get("tool_calls") or []
                    first_call = tool_calls[0] if isinstance(tool_calls, list) and tool_calls else None
                    function = first_call.get("function", first_call) if isinstance(first_call, dict) else None
                    if isinstance(function, dict) and function.get("name"):
                        output = json.dumps(function, ensure_ascii=False)
                    elif isinstance(message.get("reasoning_content"), str) and message.get("reasoning_content").strip():
                        output = message.get("reasoning_content").strip()
                actual_model = data.get("model") or model_id
                if not output.strip():
                    error_msg = "model returned no textual action"
                    metadata = {
                        "response_id": data.get("id"),
                        "finish_reason": choice.get("finish_reason"),
                        "usage": data.get("usage"),
                        "raw_model": data.get("model"),
                        "http_status": status,
                        "token_budget_repaired": token_budget_repaired,
                    }
                    return RoutingExecutionResult(
                        requested_model=model_id, actual_model=str(actual_model or ""), provider="unknown",
                        output="", latency_ms=latency_ms, cost=0.0, success=False, error=error_msg,
                        metadata=metadata, status=ExecutionStatus.MALFORMED_RESPONSE.value,
                    )
                finish_reason = choice.get("finish_reason")
                usage = data.get("usage")
                response_id = data.get("id")

                # Tentar inferir provider do actual_model (formato provider/model)
                provider = "unknown"
                if "/" in actual_model:
                    provider = actual_model.split("/")[0]

                metadata = {
                    "response_id": response_id,
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "raw_model": data.get("model"),
                    "correlation_id": data.get("correlation_id"),
                    "http_status": status,
                    "token_budget_repaired": token_budget_repaired,
                }
                execution_status = ExecutionStatus.SUCCESS

                return RoutingExecutionResult(
                    requested_model=model_id,
                    actual_model=actual_model,
                    provider=provider,
                    output=output,
                    latency_ms=latency_ms,
                    cost=0.0,  # OmniRoute não retorna custo na response
                    success=True,
                    error=None,
                    metadata=metadata,
                    status=execution_status.value,
                )

            # Erro HTTP com corpo estruturado (ex: billing_error)
            error_msg = "Unknown error"
            error_metadata = {
                "http_status": status,
                "raw_response": data,
                "token_budget_repaired": token_budget_repaired,
            }
            error_type = None
            error_code = None

            if isinstance(data, dict):
                err = data.get("error", {})
                if isinstance(err, dict):
                    error_msg = err.get("message", str(err))
                    error_type = err.get("type")
                    error_code = err.get("code")
                    # Preservar diagnostics se existir
                    if "diagnostics" in data:
                        error_metadata["diagnostics"] = data["diagnostics"]
                    if "correlation_id" in data:
                        error_metadata["correlation_id"] = data["correlation_id"]

            error_metadata["error_type"] = error_type
            error_metadata["error_code"] = error_code

            execution_status = classify_execution_error(
                http_status=status,
                error_type=error_type,
                error_code=error_code,
                error_message=error_msg,
                metadata=error_metadata,
            )

            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=latency_ms,
                cost=0.0,
                success=False,
                error=error_msg,
                metadata=error_metadata,
                status=execution_status.value,
            )

        except HTTPError as e:
            latency_ms = _elapsed_ms(start)
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                err = err_body.get("error", {})
                error_msg = err.get("message", f"HTTP {e.code}")
                metadata = {
                    "http_status": e.code,
                    "error_type": err.get("type"),
                    "error_code": err.get("code"),
                    "diagnostics": err_body.get("diagnostics"),
                    "correlation_id": err_body.get("correlation_id"),
                }
            except Exception:
                error_msg = f"HTTP {e.code}: {e.reason}"
                metadata = {"http_status": e.code}

            execution_status = classify_execution_error(
                http_status=e.code,
                error_type=metadata.get("error_type"),
                error_code=metadata.get("error_code"),
                error_message=error_msg,
                metadata=metadata,
            )

            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=latency_ms,
                cost=0.0,
                success=False,
                error=error_msg,
                metadata=metadata,
                status=execution_status.value,
            )

        except (TimeoutError, socket.timeout) as e:
            latency_ms = _elapsed_ms(start)
            error_msg = f"Timeout: the model did not respond within {self._timeout:g} seconds"
            metadata = {"error_class": type(e).__name__, "endpoint": "/v1/chat/completions"}

            execution_status = classify_execution_error(
                error_message=error_msg,
                metadata=metadata,
            )

            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=latency_ms,
                cost=0.0,
                success=False,
                error=error_msg,
                metadata=metadata,
                status=execution_status.value,
            )

        except URLError as e:
            latency_ms = _elapsed_ms(start)
            reason = getattr(e, "reason", None)
            timed_out = isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(e).lower()
            error_msg = (
                f"Timeout: the model did not respond within {self._timeout:g} seconds"
                if timed_out else f"Network error: {type(e).__name__}: {e}"
            )
            metadata = {
                "error_class": "TimeoutError" if timed_out else type(e).__name__,
                "endpoint": "/v1/chat/completions",
            }
            execution_status = classify_execution_error(
                error_message=error_msg,
                metadata=metadata,
            )
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=latency_ms,
                cost=0.0,
                success=False,
                error=error_msg,
                metadata=metadata,
                status=execution_status.value,
            )

        except Exception as e:
            latency_ms = _elapsed_ms(start)
            error_msg = f"Unexpected error: {type(e).__name__}: {e}"
            metadata = {"error_class": type(e).__name__}

            execution_status = classify_execution_error(
                error_message=error_msg,
                metadata=metadata,
            )

            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=latency_ms,
                cost=0.0,
                success=False,
                error=error_msg,
                metadata=metadata,
                status=execution_status.value,
            )


# Verificação de protocolo em tempo de importação
assert isinstance(OmniRouteAdapter, type), "OmniRouteAdapter deve ser uma classe"
_adapter_check = OmniRouteAdapter()
assert hasattr(_adapter_check, "list_models"), "Falta list_models"
assert hasattr(_adapter_check, "health"), "Falta health"
assert hasattr(_adapter_check, "execute"), "Falta execute"
# Não é necessário isinstance(..., RoutingAdapter) aqui pois Protocol
# usa structural subtyping; o check real ocorre no isinstance() em tempo de execução.
