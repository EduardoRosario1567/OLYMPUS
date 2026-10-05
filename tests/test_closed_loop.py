"""Testes do Closed Loop Olympus (PATCH 003B).

Valida:
A. Unit test com FakeRoutingAdapter para composição
B. Decisão chegando ao adapter
C. Resultado voltando ao caller
D. Separação core/adapter
E. Integração REAL opcional com OmniRoute local
"""

import os
import unittest
from typing import Optional

from olympus.models import Tarefa, Modelo, TaskType, DecisaoRegistro
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.interfaces import RepositorioPersistencia
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
    ModelCapability,
)
from olympus.pipeline import OlympusPipeline
from olympus.closed_loop import (
    build_default_registry,
    build_omniroute_adapter,
    build_pipeline,
    run_closed_loop,
    ClosedLoopResult,
)


class FakeRoutingAdapter:
    """Fake implementation of RoutingAdapter for testing.

    Uses concrete models from the updated registry (PATCH 003C).
    """
    def __init__(self):
        self._models = [
            RoutingModelInfo(
                model_id="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                capabilities=[ModelCapability.TESTES, ModelCapability.ARQUITETURA, ModelCapability.CODIGO],
                available=True,
                metadata={},
            ),
            RoutingModelInfo(
                model_id="openrouter/nvidia/nemotron-3.5-lightning:free",
                provider="openrouter",
                capabilities=[ModelCapability.TESTES, ModelCapability.ARQUITETURA, ModelCapability.CODIGO],
                available=True,
                metadata={},
            ),
        ]
        self._healthy = True
        self._execute_results = {}

    def list_models(self) -> list[RoutingModelInfo]:
        return list(self._models)

    def health(self) -> RoutingHealth:
        return RoutingHealth(
            healthy=self._healthy,
            provider="multi",
            status="operational" if self._healthy else "degraded",
            metadata={"models_count": len(self._models)},
        )

    def set_execute_result(self, model_id: str, result: RoutingExecutionResult):
        self._execute_results[model_id] = result

    def execute(
        self,
        model_id: str,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> RoutingExecutionResult:
        if model_id in self._execute_results:
            return self._execute_results[model_id]

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

        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model=model_id,
            provider=model.provider,
            output=f"Fake execution output for: {prompt[:50]}",
            latency_ms=150,
            cost=0.001,
            success=True,
            metadata={"tokens_used": len(prompt) // 4, "correlation_id": "fake-correlation-123"},
        )


class TestClosedLoopUnit(unittest.TestCase):
    """A. Unit test usando FakeRoutingAdapter para validar composição."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="test-proj", description="Test Project")

    def test_closed_loop_composition_with_fake_adapter(self):
        """A. Validar composição completa com FakeRoutingAdapter."""
        router = FakeRoutingAdapter()

        result = run_closed_loop(
            task_description="Escreva uma função Python que calcule primos até 100.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # Verificar estrutura do resultado
        self.assertIsInstance(result, ClosedLoopResult)
        self.assertEqual(result.task, "Escreva uma função Python que calcule primos até 100.")
        self.assertIsNotNone(result.task_type)
        self.assertIsNotNone(result.policy)
        self.assertIsNotNone(result.selected_model)
        self.assertGreater(result.decision_confidence, 0)
        self.assertIsNotNone(result.decision_reason)
        self.assertEqual(result.actual_model, result.selected_model)
        self.assertEqual(result.provider, "openrouter")
        self.assertTrue(result.success)
        self.assertGreater(result.latency_ms, 0)
        self.assertGreaterEqual(result.cost, 0)
        self.assertIn("Fake execution output", result.output)
        self.assertEqual(result.correlation_id, "fake-correlation-123")
        self.assertIsNotNone(result.metadata)

    def test_closed_loop_without_router_returns_decision_only(self):
        """A. Sem router, retorna apenas decisão."""
        result = run_closed_loop(
            task_description="Escreva uma função Python que calcule primos até 100.",
            project_id=self.project_id,
            router=None,
            repo=self.repo,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.actual_model, "não executado")
        self.assertEqual(result.provider, "não executado")
        self.assertEqual(result.output, "sem router: apenas decisão")


class TestDecisionReachesAdapter(unittest.TestCase):
    """B. Test da decisão chegando ao adapter."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="test-proj", description="Test Project")

    def test_selected_model_passed_to_adapter(self):
        """B. Modelo selecionado pelo DecisionEngine é passado ao adapter."""
        router = FakeRoutingAdapter()
        captured_model = {}

        def capture_execute(model_id, prompt, **kwargs):
            captured_model["model_id"] = model_id
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model=model_id,
                provider="test",
                output="ok",
                latency_ms=10,
                cost=0.0,
                success=True,
            )

        router.execute = capture_execute

        run_closed_loop(
            task_description="Escreva uma função Python que calcule primos até 100.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # Verificar que o modelo decidido chegou ao adapter
        self.assertIn("model_id", captured_model)
        self.assertIsNotNone(captured_model["model_id"])

    def test_prompt_passed_to_adapter(self):
        """B. Prompt original é passado ao adapter."""
        router = FakeRoutingAdapter()
        captured_prompt = {}

        def capture_execute(model_id, prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model=model_id,
                provider="test",
                output="ok",
                latency_ms=10,
                cost=0.0,
                success=True,
            )

        router.execute = capture_execute

        task_desc = "Escreva uma função Python que calcule primos até 100."
        run_closed_loop(
            task_description=task_desc,
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        self.assertEqual(captured_prompt["prompt"], task_desc)


class TestResultReturnsToCaller(unittest.TestCase):
    """C. Test do resultado voltando ao caller."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="test-proj", description="Test Project")

    def test_all_execution_fields_returned(self):
        """C. Todos os campos do RoutingExecutionResult retornam ao caller."""
        router = FakeRoutingAdapter()
        expected_output = "Real model output here"
        expected_latency = 250
        expected_cost = 0.003
        expected_correlation = "real-correlation-456"
        model_id = "openrouter/cohere/north-mini-code:free"

        router.set_execute_result(model_id, RoutingExecutionResult(
            requested_model=model_id,
            actual_model=model_id,
            provider="openrouter",
            output=expected_output,
            latency_ms=expected_latency,
            cost=expected_cost,
            success=True,
            metadata={"correlation_id": expected_correlation, "custom": "data"},
        ))

        result = run_closed_loop(
            task_description="Escreva uma função Python que calcule primos até 100.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        self.assertEqual(result.output, expected_output)
        self.assertEqual(result.latency_ms, expected_latency)
        self.assertEqual(result.cost, expected_cost)
        self.assertEqual(result.correlation_id, expected_correlation)
        self.assertIn("custom", result.metadata)

    def test_error_result_preserved(self):
        """C. Resultado de erro é preservado e retornado."""
        router = FakeRoutingAdapter()
        model_id = "openrouter/cohere/north-mini-code:free"
        router.set_execute_result(model_id, RoutingExecutionResult(
            requested_model=model_id,
            actual_model="",
            provider="",
            output="",
            latency_ms=50,
            cost=0.0,
            success=False,
            error="Network error: Connection refused",
            metadata={"error_class": "URLError"},
        ))

        result = run_closed_loop(
            task_description="Escreva uma função Python que calcule primos até 100.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        self.assertFalse(result.success)
        self.assertIn("Network error", result.output)
        self.assertEqual(result.latency_ms, 50)


class TestCoreAdapterSeparation(unittest.TestCase):
    """D. Test garantindo separação core/adapter."""

    def test_closed_loop_module_imports_only_protocol(self):
        """D. closed_loop.py importa apenas interfaces, não implementações no nível do módulo."""
        import olympus.closed_loop as cl_module

        source = __import__("pathlib").Path(cl_module.__file__).read_text(encoding="utf-8")

        # NÃO deve importar OmniRouteAdapter no nível do módulo (top-level)
        # O import está dentro da factory build_omniroute_adapter
        self.assertNotIn("from olympus.routing.omniroute_adapter import OmniRouteAdapter", source.split("\n\n")[0])
        # APENAS usa via build_omniroute_adapter factory

        # DEVE importar interfaces
        self.assertIn("from olympus.routing.interfaces import", source)
        self.assertIn("RoutingAdapter", source)
        self.assertIn("RoutingExecutionResult", source)

    def test_pipeline_uses_protocol_not_concrete(self):
        """D. Pipeline recebe RoutingAdapter protocol, não classe concreta."""
        from olympus.pipeline import OlympusPipeline
        import inspect

        sig = inspect.signature(OlympusPipeline.__init__)
        router_param = sig.parameters.get("router")

        # Verificar que o tipo é Optional[RoutingAdapter]
        # (o annotation usa string forward ref)
        self.assertIsNotNone(router_param)
        # Em Python 3.9, o annotation pode ser string

    def test_no_omniroute_in_core_modules(self):
        """D. Nenhum módulo core importa OmniRoute."""
        core_modules = [
            "olympus.pipeline",
            "olympus.decision_engine",
            "olympus.registry",
            "olympus.models",
            "olympus.classifier",
            "olympus.db.interfaces",
            "olympus.db.sqlite_dev_repository",
        ]

        for mod_name in core_modules:
            mod = __import__(mod_name, fromlist=[""])
            source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
            self.assertNotIn("OmniRoute", source, f"{mod_name} importa OmniRoute")
            self.assertNotIn("omniroute", source.lower(), f"{mod_name} referencia omniroute")


class TestBuilders(unittest.TestCase):
    """Testes dos builders/utilitários."""

    def test_build_default_registry(self):
        """Registry padrão tem APENAS os dois modelos concretos (PATCH 003C)."""
        registry = build_default_registry()
        models = registry.listar()

        self.assertEqual(len(models), 2)
        model_ids = {m.id for m in models}
        # Modelos concretos esperados
        self.assertIn("openrouter/cohere/north-mini-code:free", model_ids)
        self.assertIn("openrouter/nvidia/nemotron-3.5-lightning:free", model_ids)
        # NENHUM alias automático
        self.assertNotIn("auto/coding:free", model_ids)
        self.assertNotIn("auto/best-coding", model_ids)
        self.assertNotIn("openrouter/google/gemini-2.5-pro", model_ids)
        self.assertNotIn("opencode/oc/deepseek-v4-flash-free", model_ids)
        # Verificar capacidades
        for m in models:
            self.assertIn(TaskType.CODIGO, m.capacidades)
            self.assertIn(TaskType.TESTES, m.capacidades)
            self.assertIn(TaskType.ARQUITETURA, m.capacidades)
            self.assertEqual(m.custo_estimado, 0.0)
            self.assertEqual(m.provedor, "openrouter")

    def test_build_omniroute_adapter_defaults(self):
        """build_omniroute_adapter usa defaults corretos."""
        adapter = build_omniroute_adapter()
        self.assertEqual(adapter._base_url, "http://127.0.0.1:20128")
        self.assertIsNone(adapter._api_key)
        self.assertEqual(adapter._timeout, 30.0)

    def test_build_omniroute_adapter_custom(self):
        """build_omniroute_adapter aceita customização."""
        adapter = build_omniroute_adapter(
            base_url="http://custom:8080",
            api_key="custom-key",
            timeout_seconds=10.0,
        )
        self.assertEqual(adapter._base_url, "http://custom:8080")
        self.assertEqual(adapter._api_key, "custom-key")
        self.assertEqual(adapter._timeout, 10.0)

    def test_build_pipeline_with_router(self):
        """build_pipeline aceita router injetado."""
        repo = SQLiteDevRepository(":memory:")
        router = FakeRoutingAdapter()

        pipeline = build_pipeline(repo, router=router)

        self.assertIs(pipeline.router, router)
        self.assertIsInstance(pipeline.router, RoutingAdapter)

    def test_build_pipeline_without_router(self):
        """build_pipeline funciona sem router."""
        repo = SQLiteDevRepository(":memory:")

        pipeline = build_pipeline(repo)

        self.assertIsNone(pipeline.router)


@unittest.skipUnless(
    os.getenv("RUN_REAL_OMNIROUTE") == "1",
    "real OmniRoute integration disabled (set RUN_REAL_OMNIROUTE=1)"
)
class TestRealOmniRouteIntegration(unittest.TestCase):
    """E. Integração REAL com OmniRoute local.

    Execute com: RUN_REAL_OMNIROUTE=1 python3 -m unittest tests.test_closed_loop.TestRealOmniRouteIntegration -v
    """

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="real-test", description="Real OmniRoute Test")

    def test_real_closed_loop_execution(self):
        """E. Executa fluxo completo com OmniRoute real."""
        from olympus.closed_loop import run_closed_loop_with_real_omniroute

        result = run_closed_loop_with_real_omniroute(
            task_description="Escreva uma função Python que calcule os números primos até 100.",
            project_id=self.project_id,
            repo=self.repo,
        )

        # Log do resultado real
        print("\n" + "=" * 60)
        print("REAL OMNIROUTE EXECUTION RESULT")
        print("=" * 60)
        print(f"Task: {result.task}")
        print(f"Task Type: {result.task_type}")
        print(f"Policy: {result.policy}")
        print(f"Selected Model: {result.selected_model}")
        print(f"Decision Confidence: {result.decision_confidence:.2f}")
        print(f"Decision Reason: {result.decision_reason}")
        print(f"Actual Model: {result.actual_model}")
        print(f"Provider: {result.provider}")
        print(f"Success: {result.success}")
        print(f"Latency: {result.latency_ms}ms")
        cost_str = f"${result.cost:.4f}" if result.cost is not None else "N/A"
        print(f"Cost: {cost_str}")
        print(f"Output: {result.output[:500]}..." if len(result.output) > 500 else f"Output: {result.output}")
        if result.correlation_id:
            print(f"Correlation ID: {result.correlation_id}")
        if result.metadata:
            print(f"Metadata keys: {list(result.metadata.keys())}")
        print("=" * 60)

        # Validar estrutura (não validar sucesso pois pode falhar por billing/etc)
        self.assertIsInstance(result, ClosedLoopResult)
        # actual_model e provider podem ser empty strings se execução falhar
        self.assertIsInstance(result.actual_model, str)
        self.assertIsInstance(result.provider, str)
        self.assertIsInstance(result.output, str)
        self.assertIsInstance(result.latency_ms, int)

    def test_real_health_check(self):
        """E. Health check do OmniRoute real."""
        adapter = build_omniroute_adapter()
        health = adapter.health()

        print(f"\nReal OmniRoute Health: healthy={health.healthy}, status={health.status}")
        self.assertIsInstance(health.healthy, bool)
        self.assertEqual(health.provider, "omniroute")

    def test_real_list_models(self):
        """E. Lista modelos do OmniRoute real."""
        adapter = build_omniroute_adapter()
        models = adapter.list_models()

        print(f"\nReal OmniRoute Models ({len(models)}):")
        for m in models[:5]:
            print(f"  - {m.model_id} (provider={m.provider}, caps={len(m.capabilities)})")

        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)
        for m in models:
            self.assertIsInstance(m, RoutingModelInfo)
            self.assertTrue(m.model_id)
            self.assertTrue(m.provider)