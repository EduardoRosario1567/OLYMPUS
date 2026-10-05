"""Testes unitários do contrato de roteamento (PATCH 001).

Valida:
- Construção dos DTOs tipados
- Implementação fake compatível com RoutingAdapter
- runtime_checkable do protocolo
- execute retorna RoutingExecutionResult tipado
"""

import unittest
from dataclasses import is_dataclass
from typing import Optional

from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
    ModelCapability,
)


class FakeRoutingAdapter:
    """Implementação fake do RoutingAdapter para testes de contrato."""

    def __init__(self):
        self._models = [
            RoutingModelInfo(
                model_id="gpt-4o-mini",
                provider="openai",
                capabilities=[ModelCapability.CODIGO, ModelCapability.TEXTO],
                available=True,
                metadata={"version": "2024-07"},
            ),
            RoutingModelInfo(
                model_id="claude-sonnet-4",
                provider="anthropic",
                capabilities=[ModelCapability.ARQUITETURA, ModelCapability.CODIGO],
                available=True,
                metadata={"version": "2025-01"},
            ),
            RoutingModelInfo(
                model_id="local-llama",
                provider="local",
                capabilities=[ModelCapability.TEXTO],
                available=False,
                metadata={"reason": "gpu_offline"},
            ),
        ]
        self._healthy = True

    def list_models(self) -> list[RoutingModelInfo]:
        return list(self._models)

    def health(self) -> RoutingHealth:
        return RoutingHealth(
            healthy=self._healthy,
            provider="multi",
            status="operational" if self._healthy else "degraded",
            metadata={"models_count": len(self._models)},
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
        # Find the model
        model = next((m for m in self._models if m.model_id == model_id), None)
        if model is None:
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=0,
                cost=0.0,
                success=False,
                error=f"Model {model_id} not found",
            )

        if not model.available:
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model=model_id,
                provider=model.provider,
                output="",
                latency_ms=0,
                cost=0.0,
                success=False,
                error=f"Model {model_id} unavailable",
            )

        # Simulate successful execution
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model=model_id,
            provider=model.provider,
            output=f"Fake response for: {prompt[:50]}",
            latency_ms=150,
            cost=0.002,
            success=True,
            metadata={"tokens_used": len(prompt) // 4},
        )


class TestRoutingModelInfo(unittest.TestCase):
    """Testes do DTO RoutingModelInfo."""

    def test_construction_minimal(self):
        info = RoutingModelInfo(
            model_id="test-model",
            provider="test-provider",
            capabilities=[ModelCapability.TEXTO],
            available=True,
        )
        self.assertEqual(info.model_id, "test-model")
        self.assertEqual(info.provider, "test-provider")
        self.assertEqual(info.capabilities, [ModelCapability.TEXTO])
        self.assertTrue(info.available)
        self.assertEqual(info.metadata, {})

    def test_construction_with_metadata(self):
        info = RoutingModelInfo(
            model_id="test-model",
            provider="test-provider",
            capabilities=[ModelCapability.CODIGO, ModelCapability.ARQUITETURA],
            available=False,
            metadata={"region": "us-east-1", "version": "v2"},
        )
        self.assertFalse(info.available)
        self.assertEqual(info.metadata["region"], "us-east-1")

    def test_is_dataclass(self):
        self.assertTrue(is_dataclass(RoutingModelInfo))

    def test_frozen(self):
        info = RoutingModelInfo(
            model_id="test",
            provider="p",
            capabilities=[ModelCapability.TEXTO],
            available=True,
        )
        with self.assertRaises(Exception):  # frozen dataclass raises FrozenInstanceError
            info.model_id = "other"


class TestRoutingHealth(unittest.TestCase):
    """Testes do DTO RoutingHealth."""

    def test_construction_minimal(self):
        health = RoutingHealth(healthy=True)
        self.assertTrue(health.healthy)
        self.assertIsNone(health.provider)
        self.assertIsNone(health.status)
        self.assertEqual(health.metadata, {})

    def test_construction_full(self):
        health = RoutingHealth(
            healthy=False,
            provider="openai",
            status="rate_limited",
            metadata={"retry_after": 60},
        )
        self.assertFalse(health.healthy)
        self.assertEqual(health.provider, "openai")
        self.assertEqual(health.status, "rate_limited")
        self.assertEqual(health.metadata["retry_after"], 60)

    def test_is_dataclass(self):
        self.assertTrue(is_dataclass(RoutingHealth))

    def test_frozen(self):
        health = RoutingHealth(healthy=True)
        with self.assertRaises(Exception):
            health.healthy = False


class TestRoutingExecutionResult(unittest.TestCase):
    """Testes do DTO RoutingExecutionResult."""

    def test_construction_success(self):
        result = RoutingExecutionResult(
            requested_model="gpt-4o-mini",
            actual_model="gpt-4o-mini",
            provider="openai",
            output="Hello world",
            latency_ms=100,
            cost=0.001,
            success=True,
        )
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.latency_ms, 100)
        self.assertEqual(result.cost, 0.001)

    def test_construction_failure(self):
        result = RoutingExecutionResult(
            requested_model="missing-model",
            actual_model="",
            provider="",
            output="",
            latency_ms=0,
            cost=0.0,
            success=False,
            error="Model not found",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Model not found")

    def test_with_metadata(self):
        result = RoutingExecutionResult(
            requested_model="m",
            actual_model="m",
            provider="p",
            output="o",
            latency_ms=10,
            cost=0.1,
            success=True,
            metadata={"tokens": 100, "finish_reason": "stop"},
        )
        self.assertEqual(result.metadata["tokens"], 100)

    def test_is_dataclass(self):
        self.assertTrue(is_dataclass(RoutingExecutionResult))

    def test_frozen(self):
        result = RoutingExecutionResult(
            requested_model="m",
            actual_model="m",
            provider="p",
            output="o",
            latency_ms=10,
            cost=0.1,
            success=True,
        )
        with self.assertRaises(Exception):
            result.success = False


class TestRoutingAdapterProtocol(unittest.TestCase):
    """Testes do protocolo RoutingAdapter."""

    def test_fake_adapter_implements_protocol(self):
        """Verifica que FakeRoutingAdapter satisfaz o protocolo via isinstance."""
        adapter = FakeRoutingAdapter()
        self.assertIsInstance(adapter, RoutingAdapter)

    def test_runtime_checkable(self):
        """Verifica que RoutingAdapter é runtime_checkable."""
        # O decorador @runtime_checkable permite isinstance()
        from olympus.routing.interfaces import RoutingAdapter as ProtocolAdapter
        self.assertTrue(hasattr(ProtocolAdapter, '__instancecheck__'))

    def test_list_models_returns_typed_list(self):
        adapter = FakeRoutingAdapter()
        models = adapter.list_models()
        self.assertIsInstance(models, list)
        self.assertTrue(all(isinstance(m, RoutingModelInfo) for m in models))
        self.assertEqual(len(models), 3)

    def test_health_returns_typed_health(self):
        adapter = FakeRoutingAdapter()
        health = adapter.health()
        self.assertIsInstance(health, RoutingHealth)
        self.assertTrue(health.healthy)
        self.assertEqual(health.provider, "multi")

    def test_execute_returns_typed_result(self):
        adapter = FakeRoutingAdapter()
        result = adapter.execute("gpt-4o-mini", "Test prompt")
        self.assertIsInstance(result, RoutingExecutionResult)
        self.assertEqual(result.requested_model, "gpt-4o-mini")
        self.assertEqual(result.actual_model, "gpt-4o-mini")
        self.assertEqual(result.provider, "openai")
        self.assertTrue(result.success)
        self.assertGreater(result.latency_ms, 0)
        self.assertGreater(result.cost, 0)

    def test_execute_unavailable_model(self):
        adapter = FakeRoutingAdapter()
        result = adapter.execute("local-llama", "Test prompt")
        self.assertIsInstance(result, RoutingExecutionResult)
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("unavailable", result.error.lower())

    def test_execute_missing_model(self):
        adapter = FakeRoutingAdapter()
        result = adapter.execute("nonexistent-model", "Test prompt")
        self.assertIsInstance(result, RoutingExecutionResult)
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("not found", result.error.lower())

    def test_execute_optional_params(self):
        adapter = FakeRoutingAdapter()
        result = adapter.execute(
            "gpt-4o-mini",
            "Test prompt",
            max_tokens=100,
            temperature=0.7,
            custom_param="value",
        )
        self.assertIsInstance(result, RoutingExecutionResult)
        self.assertTrue(result.success)


class TestModelCapabilityEnum(unittest.TestCase):
    """Testes do enum ModelCapability."""

    def test_all_capabilities_exist(self):
        expected = {
            "TEXTO", "CODIGO", "ARQUITETURA", "REVISAO", "IMAGEM",
            "DOCUMENTACAO", "TESTES", "INTEGRACAO", "RESPOSTA_CURTA", "RESPOSTA_LONGA"
        }
        actual = {c.name for c in ModelCapability}
        self.assertEqual(actual, expected)

    def test_values_match_names(self):
        for cap in ModelCapability:
            self.assertEqual(cap.value, cap.name.lower())


if __name__ == "__main__":
    unittest.main()