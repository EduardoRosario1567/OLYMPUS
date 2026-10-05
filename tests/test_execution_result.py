"""Testes de persistência de ExecutionResult (PATCH 004B).

Valida que o resultado real de execução é persistido corretamente
separadamente da decisão, mantendo toda a cadeia de correlação.
"""

import unittest
import json
from olympus.models import ExecutionResult, Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline
from olympus.routing.interfaces import RoutingExecutionResult


class TestExecutionResultPersistence(unittest.TestCase):
    """Testes de persistência do ExecutionResult."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="test-proj", description="Test Project")
        # Criar execução e decision_record reais para satisfazer FKs
        self.execution_id = self.repo.criar_execucao(self.project_id)
        self.decision_record_id = self.repo.registrar_decisao(
            tarefa_id="task-1",
            modelo_escolhido="openrouter/cohere/north-mini-code:free",
            candidatos_avaliados=["openrouter/cohere/north-mini-code:free"],
            motivo="teste",
            confianca=0.9,
            decisao_status="approved",
            input_type="codigo",
            task_description="Test task",
            selected_provider="openrouter",
            policy_applied="padrao_menor_custo",
            estimated_cost=0.0,
            estimated_latency_ms=500,
            project_id=self.project_id,
            execution_id=self.execution_id,
        )

    def test_1_execution_result_pode_ser_criado(self):
        """1. execution_result pode ser criado."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="def hello():\n    return 'world'",
            latency_ms=1500,
            cost=0.0,
            success=True,
        )
        self.assertIsNotNone(result_id)
        self.assertIsInstance(result_id, str)

    def test_2_requested_model_preservado(self):
        """2. requested_model preservado."""
        requested = "openrouter/cohere/north-mini-code:free"
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model=requested,
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["requested_model"], requested)

    def test_3_actual_model_preservado(self):
        """3. actual_model preservado."""
        actual = "cohere/north-mini-code:free"
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model=actual,
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["actual_model"], actual)

    def test_4_provider_preservado(self):
        """4. provider preservado."""
        provider = "cohere"
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider=provider,
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["provider"], provider)

    def test_5_output_completo_preservado(self):
        """5. output completo preservado."""
        output = "def primos_hasta_100():\n    crivo = [False, False] + [True] * 99\n    for i in range(2, 11):\n        if crivo[i]:\n            for j in range(i*i, 101, i):\n                crivo[j] = False\n    return [i for i, e in enumerate(crivo) if e]"
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output=output,
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["output"], output)

    def test_6_latency_ms_preservado(self):
        """6. latency_ms preservado."""
        latency = 7725
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=latency,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["latency_ms"], latency)

    def test_7_cost_preservado(self):
        """7. cost preservado."""
        cost = 0.0034
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=cost,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["cost"], cost)

    def test_8_success_preservado(self):
        """8. success preservado."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertTrue(result["success"])

    def test_9_error_preservado(self):
        """9. error preservado."""
        from olympus.models import ExecutionStatus
        error = "Network error: Connection refused"
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="",
            provider="",
            output="",
            latency_ms=50,
            cost=0.0,
            success=False,
            error=error,
            status=ExecutionStatus.UNKNOWN_ERROR.value,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["error"], error)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], ExecutionStatus.UNKNOWN_ERROR.value)

    def test_10_status_preservado(self):
        """10. status preservado."""
        from olympus.models import ExecutionStatus
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
            status=ExecutionStatus.SUCCESS.value,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["status"], ExecutionStatus.SUCCESS.value)

    def test_11_correlation_id_preservado(self):
        """11. correlation_id preservado."""
        corr_id = "corr-abc-123"
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
            correlation_id=corr_id,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["correlation_id"], corr_id)

    def test_12_usage_preservado(self):
        """12. usage preservado."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
            usage=usage,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["usage"], usage)

    def test_13_metadata_preservado(self):
        """13. metadata preservado."""
        metadata = {"finish_reason": "stop", "model": "cohere/north-mini-code:free", "http_status": 200}
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
            metadata=metadata,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["metadata"], metadata)

    def test_14_decision_record_id_vinculo_preservado(self):
        """14. decision_record_id vínculo preservado."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["decision_record_id"], self.decision_record_id)

        # Busca por decision_record_id
        result2 = self.repo.obter_execution_result_por_decisao(self.decision_record_id)
        self.assertIsNotNone(result2)
        self.assertEqual(result2["decision_record_id"], self.decision_record_id)

    def test_15_execution_id_vinculo_preservado(self):
        """15. execution_id vínculo preservado."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["execution_id"], self.execution_id)

        # Lista por execution_id
        results = self.repo.listar_execution_results(execution_id=self.execution_id)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["execution_id"], self.execution_id)

    def test_16_sqlite_roundtrip_completo(self):
        """16. SQLite round-trip completo."""
        original = {
            "execution_id": self.execution_id,
            "decision_record_id": self.decision_record_id,
            "requested_model": "openrouter/cohere/north-mini-code:free",
            "actual_model": "cohere/north-mini-code:free",
            "provider": "cohere",
            "output": "def f(): pass",
            "latency_ms": 1234,
            "cost": 0.001,
            "success": True,
            "error": None,
            "status": "success",
            "correlation_id": "corr-123",
            "usage": {"tokens": 100},
            "metadata": {"finish_reason": "stop"},
        }
        result_id = self.repo.registrar_execution_result(**original)
        stored = self.repo.obter_execution_result(result_id)

        for key, value in original.items():
            self.assertEqual(stored[key], value, f"Mismatch in {key}")

    def test_17_resultado_success(self):
        """17. resultado success."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
            status="success",
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["error"])

    def test_18_resultado_failed(self):
        """18. resultado failed."""
        from olympus.models import ExecutionStatus
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="",
            provider="",
            output="",
            latency_ms=50,
            cost=0.0,
            success=False,
            error="Timeout after 30s",
            status=ExecutionStatus.TIMEOUT.value,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], ExecutionStatus.TIMEOUT.value)
        self.assertEqual(result["error"], "Timeout after 30s")

    def test_19_requested_model_diferente_actual_model_permitido(self):
        """19. requested_model != actual_model permitido."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="openrouter/nvidia/nemotron-3.5-lightning:free",
            provider="nvidia",
            output="output",
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertNotEqual(result["requested_model"], result["actual_model"])
        self.assertEqual(result["requested_model"], "openrouter/cohere/north-mini-code:free")
        self.assertEqual(result["actual_model"], "openrouter/nvidia/nemotron-3.5-lightning:free")
        self.assertEqual(result["provider"], "nvidia")

    def test_20_output_unicode_codigo_multilinha_preservado(self):
        """20. output Unicode/código multilinha preservado."""
        output = """
# -*- coding: utf-8 -*-
def primos(n):
    \"\"\"Retorna primos até n.\"\"\"
    # Comentário em português: çãõ
    return [i for i in range(2, n+1) if all(i % j != 0 for j in range(2, int(i**0.5)+1))]

print(primos(100))
# Output: [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]
"""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output=output,
            latency_ms=100,
            cost=0.0,
            success=True,
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["output"], output)


class TestExecutionResultIntegration(unittest.TestCase):
    """Testes de integração com Pipeline e Closed Loop."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="integ-proj", description="Integration Test")

    def test_pipeline_registrar_resultado_execucao(self):
        """Pipeline.registrar_resultado_execucao persiste corretamente."""
        classifier = TaskClassifier()
        registry = ModelRegistry()
        registry.registrar(Modelo(
            id="test-model", nome="Test", provedor="test",
            capacidades=[TaskType.CODIGO], custo_estimado=0.0, latencia_estimada=0.5, confiabilidade=0.9,
        ))
        engine = DecisionEngine(registry)
        pipeline = OlympusPipeline(classifier, registry, engine, self.repo)

        # Criar execução e decisão
        execution_id = pipeline.iniciar_execucao(self.project_id)
        tarefa = Tarefa(id="task-1", projeto_id=self.project_id, descricao="Implementar uma função Python")
        decisao, decision_record_id = pipeline.processar_tarefa(tarefa, self.project_id, execution_id)

        # Criar execution_result simulado
        exec_result = RoutingExecutionResult(
            requested_model=decisao.modelo_escolhido,
            actual_model="test-model",
            provider="test",
            output="real output from model",
            latency_ms=123,
            cost=0.0,
            success=True,
            metadata={"correlation_id": "corr-123", "usage": {"tokens": 50}},
        )

        # Persistir via pipeline
        result_id = pipeline.registrar_resultado_execucao(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            execution_result=exec_result,
        )

        # Verificar persistido
        stored = self.repo.obter_execution_result(result_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["requested_model"], decisao.modelo_escolhido)
        self.assertEqual(stored["actual_model"], "test-model")
        self.assertEqual(stored["provider"], "test")
        self.assertEqual(stored["output"], "real output from model")
        self.assertEqual(stored["latency_ms"], 123)
        self.assertTrue(stored["success"])
        self.assertEqual(stored["correlation_id"], "corr-123")
        self.assertEqual(stored["usage"], {"tokens": 50})

    def test_closed_loop_persiste_execution_result(self):
        """Closed loop persiste execution_result automaticamente."""
        from olympus.closed_loop import run_closed_loop, build_default_registry

        registry = build_default_registry()
        classifier = TaskClassifier()
        engine = DecisionEngine(registry)
        pipeline = OlympusPipeline(classifier, registry, engine, self.repo)

        # Mock router que retorna resultado real
        class MockRouter:
            def execute(self, model_id, prompt, **kwargs):
                return RoutingExecutionResult(
                    requested_model=model_id,
                    actual_model="cohere/north-mini-code:free",
                    provider="cohere",
                    output="def primos(): return [2,3,5,7]",
                    latency_ms=1500,
                    cost=0.0,
                    success=True,
                    metadata={"correlation_id": "real-corr-456", "usage": {"total_tokens": 200}},
                )

            def list_models(self):
                return []

            def health(self):
                from olympus.routing.interfaces import RoutingHealth
                return RoutingHealth(healthy=True, provider="test")

        router = MockRouter()
        pipeline = OlympusPipeline(classifier, registry, engine, self.repo, router=router)

        execution_id = pipeline.iniciar_execucao(self.project_id)
        tarefa = Tarefa(id="task-2", projeto_id=self.project_id, descricao="Escreva uma função Python")
        decisao, decision_record_id = pipeline.processar_tarefa(tarefa, self.project_id, execution_id)

        exec_result = pipeline.executar_decisao(decisao, tarefa.descricao)

        pipeline.registrar_resultado_execucao(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            execution_result=exec_result,
        )
        pipeline.finalizar_execucao(execution_id, [decisao])

        # Verificar que execution_result foi persistido
        results = self.repo.listar_execution_results(execution_id=execution_id)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["actual_model"], "cohere/north-mini-code:free")
        self.assertEqual(results[0]["provider"], "cohere")
        self.assertEqual(results[0]["output"], "def primos(): return [2,3,5,7]")
        self.assertEqual(results[0]["latency_ms"], 1500)
        self.assertTrue(results[0]["success"])
        self.assertEqual(results[0]["correlation_id"], "real-corr-456")


if __name__ == "__main__":
    unittest.main()