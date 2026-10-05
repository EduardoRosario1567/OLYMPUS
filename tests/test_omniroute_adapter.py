"""Testes unitários do OmniRouteAdapter (PATCH 002B).

Valida implementação contra o contrato RoutingAdapter usando HTTP server fake.
SEM dependência do OmniRoute real.
"""

import json
import socket
import threading
import time
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import unittest

from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
    ModelCapability,
)
from olympus.routing.omniroute_adapter import OmniRouteAdapter, _decode_response_body


class FakeOmniRouteHandler(BaseHTTPRequestHandler):
    """Handler HTTP que simula endpoints do OmniRoute."""

    # Configuração de resposta por endpoint (class-level, shared)
    responses = {
        "/v1/models": {
            "status": 200,
            "body": {
                "object": "list",
                "data": [
                    {
                        "id": "auto/best-coding",
                        "object": "model",
                        "created": 1787943770,
                        "owned_by": "combo",
                        "permission": [],
                        "root": "auto/best-coding",
                        "parent": None,
                        "context_length": 1000000,
                        "max_input_tokens": 1000000,
                        "max_output_tokens": 384000,
                        "capabilities": {
                            "tool_calling": True,
                            "reasoning": True,
                            "thinking": True,
                            "temperature": True
                        }
                    },
                    {
                        "id": "openrouter/google/gemini-2.5-pro",
                        "object": "model",
                        "created": 1787943770,
                        "owned_by": "openrouter",
                        "permission": [],
                        "root": "openrouter/google/gemini-2.5-pro",
                        "parent": None,
                        "context_length": 1000000,
                        "max_input_tokens": 1000000,
                        "max_output_tokens": 384000,
                        "capabilities": {
                            "vision": True,
                            "tool_calling": True,
                            "reasoning": True
                        }
                    },
                    {
                        "id": "opencode/oc/deepseek-v4-flash-free",
                        "object": "model",
                        "created": 1787943770,
                        "owned_by": "opencode",
                        "permission": [],
                        "root": "opencode/oc/deepseek-v4-flash-free",
                        "parent": None,
                        "context_length": 100000,
                        "max_input_tokens": 50000,
                        "max_output_tokens": 4000,
                        "capabilities": {
                            "tool_calling": True,
                            "reasoning": True,
                            "unknown_capability": True  # capability desconhecida
                        }
                    },
                    {
                        "id": "auto/coding:free",
                        "object": "model",
                        "created": 1787943770,
                        "owned_by": "combo",
                        "permission": [],
                        "root": "auto/coding:free",
                        "parent": None,
                        "context_length": 1000000,
                        "max_input_tokens": 1000000,
                        "max_output_tokens": 384000,
                        "capabilities": {
                            "tool_calling": True,
                            "reasoning": True
                        }
                    }
                ]
            }
        },
        "/v1/chat/completions": {
            "status": 200,
            "body": {
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1787943770,
                "model": "auto/best-coding",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Hello! How can I help you?"
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
            }
        }
    }

    # Error config stored on server instance (set via FakeServer)
    error_config: Optional[dict] = None

    def do_GET(self):
        if self.path in self.responses:
            resp = self.responses[self.path]
            self.send_response(resp["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp["body"]).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not found"}')

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        # Verificar Authorization header
        auth_header = self.headers.get("Authorization", "")
        # Store on server instance for test retrieval
        self.server.last_auth = auth_header
        self.server.last_body = json.loads(body) if body else {}

        if self.error_config:
            self.send_response(self.error_config.get("status", 500))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.error_config.get("body", {})).encode())
            return

        if self.path in self.responses:
            resp = self.responses[self.path]
            self.send_response(resp["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp["body"]).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not found"}')

    def log_message(self, format, *args):
        pass  # Silenciar logs


class FakeServer:
    """Servidor HTTP fake para testes."""

    def __init__(self, port: int = 0):
        self.server = HTTPServer(("127.0.0.1", port), FakeOmniRouteHandler)
        self.server.last_auth = ""
        self.server.last_body = {}
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.1)  # Aguardar servidor iniciar

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def set_error(self, status: int, body: dict):
        """Configura resposta de erro para próximas requisições."""
        self.server.RequestHandlerClass.error_config = {"status": status, "body": body}

    def clear_error(self):
        self.server.RequestHandlerClass.error_config = None

    def get_last_auth(self) -> str:
        return getattr(self.server, "last_auth", "")

    def get_last_body(self) -> dict:
        return getattr(self.server, "last_body", {})

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)


class TestOmniRouteAdapter(unittest.TestCase):
    """Testes do OmniRouteAdapter contra servidor fake."""

    @classmethod
    def setUpClass(cls):
        cls.server = FakeServer()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.server.clear_error()
        self.adapter = OmniRouteAdapter(
            base_url=self.server.get_url(),
            api_key="test-key-123",
            timeout_seconds=5.0,
        )

    def test_adapter_implements_protocol(self):
        """Verifica que OmniRouteAdapter satisfaz RoutingAdapter."""
        self.assertIsInstance(self.adapter, RoutingAdapter)

    def test_sse_is_normalized_when_gateway_ignores_non_stream_request(self):
        raw = "\n".join([
            'data: {"id":"chat-1","object":"chat.completion.chunk","created":1,"model":"route/model","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}',
            'data: {"id":"chat-1","object":"chat.completion.chunk","created":1,"model":"route/model","choices":[{"index":0,"delta":{"reasoning_content":"thinking"},"finish_reason":null}]}',
            'data: {"id":"chat-1","object":"chat.completion.chunk","created":1,"model":"route/model","choices":[{"index":0,"delta":{"content":"OLYMPUS OK"},"finish_reason":null}]}',
            'data: {"id":"chat-1","object":"chat.completion.chunk","created":1,"model":"route/model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"total_tokens":61}}',
            "data: [DONE]",
        ])
        decoded = _decode_response_body(raw)
        self.assertEqual(decoded["choices"][0]["message"]["content"], "OLYMPUS OK")
        self.assertEqual(decoded["choices"][0]["message"]["reasoning_content"], "thinking")
        self.assertEqual(decoded["choices"][0]["finish_reason"], "stop")
        self.assertEqual(decoded["usage"]["total_tokens"], 61)

    def test_list_models_success(self):
        """list_models retorna lista tipada de RoutingModelInfo."""
        models = self.adapter.list_models()
        self.assertIsInstance(models, list)
        self.assertEqual(len(models), 4)
        for m in models:
            self.assertIsInstance(m, RoutingModelInfo)
            self.assertTrue(m.available)
            self.assertIsInstance(m.capabilities, list)
            self.assertTrue(all(isinstance(c, ModelCapability) for c in m.capabilities))

    def test_list_models_capabilities_mapping(self):
        """Verifica mapeamento de capabilities conhecidas."""
        models = self.adapter.list_models()

        # auto/best-coding -> combo, capabilities: tool_calling, reasoning, thinking, temperature
        auto_coding = next(m for m in models if m.model_id == "auto/best-coding")
        self.assertEqual(auto_coding.provider, "combo")
        self.assertIn(ModelCapability.TESTES, auto_coding.capabilities)  # tool_calling
        self.assertIn(ModelCapability.ARQUITETURA, auto_coding.capabilities)  # reasoning/thinking
        self.assertIn(ModelCapability.TEXTO, auto_coding.capabilities)  # temperature

        # openrouter/google/gemini-2.5-pro -> openrouter, capabilities: vision, tool_calling, reasoning
        gemini = next(m for m in models if m.model_id == "openrouter/google/gemini-2.5-pro")
        self.assertEqual(gemini.provider, "openrouter")
        self.assertIn(ModelCapability.IMAGEM, gemini.capabilities)  # vision
        self.assertIn(ModelCapability.TESTES, gemini.capabilities)  # tool_calling
        self.assertIn(ModelCapability.ARQUITETURA, gemini.capabilities)  # reasoning

    def test_list_models_unknown_capabilities_preserved(self):
        """Capabilities desconhecidas são preservadas em metadata."""
        models = self.adapter.list_models()
        opencode_model = next(m for m in models if m.model_id == "opencode/oc/deepseek-v4-flash-free")
        self.assertIn("capabilities_raw", opencode_model.metadata)
        self.assertTrue(opencode_model.metadata["capabilities_raw"].get("unknown_capability"))
        # unknown_capability NÃO deve quebrar o parsing
        # Deve ter pelo menos as conhecidas
        self.assertIn(ModelCapability.TESTES, opencode_model.capabilities)
        self.assertIn(ModelCapability.ARQUITETURA, opencode_model.capabilities)

    def test_list_models_metadata_preserved(self):
        """Metadata preserva campos úteis do OmniRoute."""
        models = self.adapter.list_models()
        m = models[0]
        self.assertIn("context_length", m.metadata)
        self.assertIn("max_input_tokens", m.metadata)
        self.assertIn("max_output_tokens", m.metadata)
        self.assertIn("root", m.metadata)
        self.assertIn("owned_by", m.metadata)
        self.assertIn("capabilities_raw", m.metadata)
        self.assertEqual(m.metadata["owned_by"], m.provider)

    def test_health_healthy(self):
        """health retorna healthy=true quando servidor responde."""
        health = self.adapter.health()
        self.assertIsInstance(health, RoutingHealth)
        self.assertTrue(health.healthy)
        self.assertEqual(health.provider, "omniroute")
        self.assertEqual(health.status, "liveness_ok")
        self.assertIn("check_type", health.metadata)
        self.assertEqual(health.metadata["check_type"], "liveness")
        self.assertIn("latency_ms", health.metadata)
        self.assertIn("models_count", health.metadata)
        self.assertEqual(health.metadata["models_count"], 4)

    def test_health_server_unavailable(self):
        """health retorna healthy=false quando servidor indisponível."""
        # Criar adapter para porta inexistente
        adapter = OmniRouteAdapter(
            base_url="http://127.0.0.1:9999",
            timeout_seconds=0.5,
        )
        health = adapter.health()
        self.assertFalse(health.healthy)
        self.assertEqual(health.provider, "omniroute")
        self.assertEqual(health.status, "unreachable")
        self.assertIn("error", health.metadata)

    def test_execute_success(self):
        """execute retorna RoutingExecutionResult tipado em sucesso."""
        result = self.adapter.execute("auto/best-coding", "Hello world")
        self.assertIsInstance(result, RoutingExecutionResult)
        self.assertEqual(result.requested_model, "auto/best-coding")
        self.assertEqual(result.actual_model, "auto/best-coding")
        self.assertEqual(result.provider, "auto")  # inferido do actual_model
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertGreater(result.latency_ms, 0)
        self.assertEqual(result.cost, 0.0)
        self.assertEqual(result.output, "Hello! How can I help you?")
        self.assertIn("response_id", result.metadata)
        self.assertIn("finish_reason", result.metadata)
        self.assertIn("usage", result.metadata)

    def test_execute_requested_vs_actual_model(self):
        """requested_model preservado; actual_model vem da response."""
        result = self.adapter.execute("auto/coding:free", "Test prompt")
        self.assertEqual(result.requested_model, "auto/coding:free")
        self.assertEqual(result.actual_model, "auto/best-coding")  # resposta do fake server

    def test_execute_max_tokens_temperature_optional(self):
        """max_tokens e temperature são opcionais e enviados quando fornecidos."""
        self.adapter.execute("auto/best-coding", "Test", max_tokens=100, temperature=0.5)
        body = self.server.get_last_body()
        self.assertEqual(body.get("max_tokens"), 100)
        self.assertEqual(body.get("temperature"), 0.5)

        # Sem parâmetros opcionais
        self.server.clear_error()
        self.adapter.execute("auto/best-coding", "Test")
        body = self.server.get_last_body()
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("temperature", body)

    def test_execute_repairs_provider_max_tokens_limit_and_retries_same_model(self):
        adapter = OmniRouteAdapter(base_url="http://example.invalid")
        payloads = []
        responses = iter((
            HTTPError(
                "http://example.invalid/v1/chat/completions",
                400,
                "Bad Request",
                {},
                BytesIO(json.dumps({"error": {
                    "message": "max_tokens must be less than or equal to 1024",
                    "type": "invalid_request_error",
                }}).encode("utf-8")),
            ),
            (200, {
                "id": "retry-ok",
                "model": "cohere/north-mini-code:free",
                "choices": [{"message": {"content": '{"type":"finish"}'}}],
            }),
        ))

        def request(_method, _path, payload=None):
            payloads.append(dict(payload or {}))
            response = next(responses)
            if isinstance(response, HTTPError):
                raise response
            return response

        adapter._make_request = request
        result = adapter.execute("cohere/north-mini-code:free", "return JSON", max_tokens=4096)

        self.assertTrue(result.success)
        self.assertEqual(payloads[0]["max_tokens"], 4096)
        self.assertEqual(payloads[1]["max_tokens"], 1024)
        self.assertTrue(result.metadata["token_budget_repaired"])

    def test_execute_http_error_with_diagnostics(self):
        """HTTP error com error+diagnostics retorna RoutingExecutionResult com success=False."""
        self.server.set_error(402, {
            "error": {
                "message": "[402]: Insufficient credits",
                "type": "billing_error",
                "code": "payment_required"
            },
            "diagnostics": {
                "poolSize": 13,
                "attempted": 4,
                "excluded": [{"provider": "openrouter", "reason": "exhausted"}],
                "attemptOrder": [{"provider": "opencode", "model": "oc/big-pickle"}],
                "terminalReason": "Insufficient credits",
                "recovery": {"action": "retry"},
                "recovery_hint": {"action": "retry"}
            },
            "correlation_id": "test-correlation-123"
        })

        result = self.adapter.execute("auto/best-coding", "Test")
        self.assertFalse(result.success)
        self.assertEqual(result.requested_model, "auto/best-coding")
        self.assertIn("Insufficient credits", result.error)
        self.assertIn("diagnostics", result.metadata)
        self.assertEqual(result.metadata["correlation_id"], "test-correlation-123")
        self.assertEqual(result.metadata["error_code"], "payment_required")

    def test_execute_timeout_network_error(self):
        """Timeout/network error retorna RoutingExecutionResult com success=False."""
        # Adapter com timeout muito baixo para forçar timeout
        adapter = OmniRouteAdapter(
            base_url="http://127.0.0.1:9999",
            timeout_seconds=0.001,
        )
        result = adapter.execute("auto/best-coding", "Test")
        self.assertFalse(result.success)
        self.assertIn("Network error", result.error)
        self.assertEqual(result.requested_model, "auto/best-coding")

    def test_api_key_sent_when_configured(self):
        """Authorization header enviado quando api_key configurada."""
        self.adapter.execute("auto/best-coding", "Test")
        auth = self.server.get_last_auth()
        self.assertEqual(auth, "Bearer test-key-123")

    def test_api_key_absent_when_not_configured(self):
        """Authorization header NÃO enviado quando api_key não configurada."""
        adapter_no_key = OmniRouteAdapter(base_url=self.server.get_url(), api_key=None)
        adapter_no_key.execute("auto/best-coding", "Test")
        auth = self.server.get_last_auth()
        self.assertEqual(auth, "")

    def test_api_key_never_in_result(self):
        """API key nunca aparece no RoutingExecutionResult."""
        result = self.adapter.execute("auto/best-coding", "Test")
        # Verificar que metadata não contém a key
        result_str = json.dumps(result.metadata, default=str)
        self.assertNotIn("test-key-123", result_str)
        self.assertNotIn("Bearer", result_str)

    def test_alias_auto_coding_free_sent_without_transformation(self):
        """Alias auto/coding:free é enviado sem transformação."""
        self.adapter.execute("auto/coding:free", "Test")
        body = self.server.get_last_body()
        self.assertEqual(body.get("model"), "auto/coding:free")

    def test_execute_specific_provider_model(self):
        """Modelo específico (openrouter/...) enviado sem transformação."""
        self.adapter.execute("openrouter/google/gemini-2.5-pro", "Test")
        body = self.server.get_last_body()
        self.assertEqual(body.get("model"), "openrouter/google/gemini-2.5-pro")

    def test_execute_opencode_model(self):
        """Modelo opencode/... enviado sem transformação."""
        self.adapter.execute("opencode/oc/deepseek-v4-flash-free", "Test")
        body = self.server.get_last_body()
        self.assertEqual(body.get("model"), "opencode/oc/deepseek-v4-flash-free")


class TestOmniRouteAdapterNoServer(unittest.TestCase):
    """Testes que não requerem servidor (erros de init, etc.)."""

    def test_constructor_defaults(self):
        """Constructor com valores padrão."""
        adapter = OmniRouteAdapter()
        self.assertEqual(adapter._base_url, "http://127.0.0.1:20128")
        self.assertIsNone(adapter._api_key)
        self.assertEqual(adapter._timeout, 180.0)

    def test_socket_timeout_is_typed_and_never_unexpected(self):
        adapter = OmniRouteAdapter(timeout_seconds=180)
        adapter._make_request = lambda *args, **kwargs: (_ for _ in ()).throw(
            socket.timeout("timed out")
        )
        result = adapter.execute("openrouter/openrouter/free", "Test")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "timeout")
        self.assertIn("180 seconds", result.error)
        self.assertNotIn("Unexpected", result.error)

    def test_nested_url_timeout_is_typed(self):
        adapter = OmniRouteAdapter(timeout_seconds=180)
        adapter._make_request = lambda *args, **kwargs: (_ for _ in ()).throw(
            URLError(socket.timeout("timed out"))
        )
        result = adapter.execute("openrouter/openrouter/free", "Test")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "timeout")
        self.assertNotIn("Unexpected", result.error)

    def test_constructor_custom_values(self):
        """Constructor com valores customizados."""
        adapter = OmniRouteAdapter(
            base_url="http://custom:8080",
            api_key="custom-key",
            timeout_seconds=10.0,
        )
        self.assertEqual(adapter._base_url, "http://custom:8080")
        self.assertEqual(adapter._api_key, "custom-key")
        self.assertEqual(adapter._timeout, 10.0)

    def test_base_url_trailing_slash_stripped(self):
        """Trailing slash removido do base_url."""
        adapter = OmniRouteAdapter(base_url="http://test:8080/")
        self.assertEqual(adapter._base_url, "http://test:8080")


class TestRoutingContractStillWorks(unittest.TestCase):
    """Verifica que contrato RoutingAdapter não foi quebrado."""

    def test_protocol_runtime_checkable(self):
        from olympus.routing.interfaces import RoutingAdapter
        # @runtime_checkable permite isinstance
        adapter = OmniRouteAdapter(base_url="http://invalid")
        self.assertIsInstance(adapter, RoutingAdapter)


if __name__ == "__main__":
    unittest.main()
