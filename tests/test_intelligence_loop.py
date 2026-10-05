"""
Testes do Intelligence Loop — PATCH 005E

Valida integração completa:
Decision → Execution → RuleBasedJudge Evaluation → QualityEvaluation Persistence

Zero dependências externas, zero chamadas de rede/LLM nos testes unitários.
"""

import os
import unittest
from typing import Optional

from olympus.models import Tarefa, TaskType, Modelo
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
    ModelCapability,
)
from olympus.intelligence_loop import (
    run_intelligence_loop,
    run_intelligence_loop_with_real_omniroute,
    build_judge_context,
    build_judge,
    IntelligenceLoopResult,
)
from olympus.judge.interfaces import JudgeContext, JudgeResult, EvaluationPolicy
from olympus.judge.rule_based import RuleBasedJudge
from olympus.judge.policies import default_codigo_policy, to_simple_policy


class FakeRoutingAdapter:
    """Fake implementation of RoutingAdapter for testing."""

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


class FakeJudge:
    """Fake JudgeAdapter para testes unitários."""

    def __init__(self, fixed_result: Optional[JudgeResult] = None):
        self._fixed_result = fixed_result

    def evaluate(self, context: JudgeContext) -> JudgeResult:
        if self._fixed_result is not None:
            return self._fixed_result
        return JudgeResult(
            quality_score=0.8,
            passed=True,
            evaluator="fake",
            reason="fake evaluation",
            criteria={"fake_criterion": 0.8},
            metadata={"context_task_id": context.task_id},
        )


class TestIntelligenceLoopUnit(unittest.TestCase):
    """Testes unitários com FakeRoutingAdapter e FakeJudge."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(
            name="Test Project",
            description="Test",
            product_type=None,
            complexity=None,
            status="active"
        )

    def test_1_decision_execution_evaluation_chain(self):
        """1. Fluxo completo: decision → execution → evaluation."""
        # Usar FakeRoutingAdapter que retorna sucesso
        router = FakeRoutingAdapter()
        # Configurar resposta
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def primes(n):\n    return [i for i in range(2, n+1) if all(i % j != 0 for j in range(2, int(i**0.5)+1))]",
                latency_ms=1000,
                cost=0.0,
                success=True,
                status="success",
                metadata={"correlation_id": "test-corr-123"},
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python que calcule os números primos até 100.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # Verificar estrutura do resultado
        self.assertIsInstance(result, IntelligenceLoopResult)
        self.assertEqual(result.task, "Escreva uma função Python que calcule os números primos até 100.")
        self.assertEqual(result.task_type, "codigo")

        # Decision
        self.assertIn("selected_model", result.decision)
        self.assertIn("confidence", result.decision)
        self.assertIn("reason", result.decision)
        self.assertIn("decision_record_id", result.decision)

        # Execution
        self.assertEqual(result.execution["actual_model"], "openrouter/cohere/north-mini-code:free")
        self.assertEqual(result.execution["provider"], "openrouter")
        self.assertEqual(result.execution["status"], "success")
        self.assertTrue(result.execution["success"])
        self.assertEqual(result.execution["latency_ms"], 1000)
        self.assertEqual(result.execution["cost"], 0.0)
        self.assertIn("def primes", result.execution["output"])
        self.assertEqual(result.execution["correlation_id"], "test-corr-123")
        self.assertIsNotNone(result.execution["execution_result_id"])

        # Evaluation
        self.assertIsNotNone(result.evaluation["quality_score"])
        self.assertIsNotNone(result.evaluation["passed"])
        self.assertEqual(result.evaluation["evaluator"], "rule_based")
        self.assertIsNotNone(result.evaluation["reason"])
        self.assertIsNotNone(result.evaluation["criteria"])

        # Persistence
        self.assertIsNotNone(result.quality_evaluation_id)

    def test_2_execution_result_to_judge_context(self):
        """2. ExecutionResult → JudgeContext mapeamento correto."""
        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def hello(): pass",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
                metadata={"correlation_id": "corr-123", "usage": {"tokens": 100}},
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python simples.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # Verificar que JudgeContext foi construído corretamente
        # (indiretamente via evaluation criteria)
        self.assertIn("non_empty_output", result.evaluation["criteria"])
        self.assertIn("minimum_content", result.evaluation["criteria"])
        self.assertIn("expected_structure", result.evaluation["criteria"])

    def test_3_judge_result_to_quality_evaluation(self):
        """3. JudgeResult → QualityEvaluation persistence."""
        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def test(): return 1",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python que retorne 1.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # Verificar persistência
        self.assertIsNotNone(result.quality_evaluation_id)

        # Consultar persistência
        stored = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["id"], result.quality_evaluation_id)
        self.assertEqual(stored["execution_result_id"], result.execution["execution_result_id"])
        self.assertEqual(stored["quality_score"], result.evaluation["quality_score"])
        self.assertEqual(stored["passed"], result.evaluation["passed"])
        self.assertEqual(stored["evaluator"], result.evaluation["evaluator"])
        self.assertEqual(stored["reason"], result.evaluation["reason"])
        self.assertEqual(stored["criteria"], result.evaluation["criteria"])

    def test_4_persistence_chain(self):
        """4. Cadeia de persistência completa: DecisionRecord → ExecutionResult → QualityEvaluation."""
        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def primes(): pass",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python para primos.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # DecisionRecord
        decision = self.repo.obter_decisao(result.decision["decision_record_id"])
        self.assertIsNotNone(decision)

        # ExecutionResult
        exec_result = self.repo.obter_execution_result(result.execution["execution_result_id"])
        self.assertIsNotNone(exec_result)
        self.assertEqual(exec_result["decision_record_id"], result.decision["decision_record_id"])

        # QualityEvaluation
        quality_eval = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertIsNotNone(quality_eval)
        self.assertEqual(quality_eval["execution_result_id"], result.execution["execution_result_id"])

    def test_5_evaluation_failure_nao_altera_decision(self):
        """5. Falha na avaliação não altera DecisionRecord."""
        router = FakeRoutingAdapter()
        # Resposta com output vazio → quality_score = 0
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="",  # vazio
                latency_ms=100,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python simples.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # DecisionRecord permanece intacto
        decision = self.repo.obter_decisao(result.decision["decision_record_id"])
        self.assertIsNotNone(decision)
        self.assertEqual(decision["selected_model"], "openrouter/cohere/north-mini-code:free")

        # ExecutionResult permanece intacto
        exec_result = self.repo.obter_execution_result(result.execution["execution_result_id"])
        self.assertIsNotNone(exec_result)
        self.assertEqual(exec_result["output"], "")

        # QualityEvaluation registra score baixo
        quality_eval = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertIsNotNone(quality_eval)
        self.assertEqual(quality_eval["quality_score"], 0.0)
        self.assertFalse(quality_eval["passed"])

    def test_6_quality_score_preservado(self):
        """6. Quality score preservado exatamente."""
        # Usar FakeJudge com resultado fixo
        fixed_result = JudgeResult(
            quality_score=0.75,
            passed=True,
            evaluator="fake",
            reason="fixed score",
            criteria={"test": 0.75},
            metadata={},
        )
        fake_judge = FakeJudge(fixed_result=fixed_result)

        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def test(): pass",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python simples.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
            judge=fake_judge,
        )

        self.assertEqual(result.evaluation["quality_score"], 0.75)
        stored = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertEqual(stored["quality_score"], 0.75)

    def test_7_passed_preservado(self):
        """7. Passed preservado exatamente."""
        fixed_result = JudgeResult(
            quality_score=0.9,
            passed=True,
            evaluator="fake",
            reason="passed",
            criteria={"test": 0.9},
            metadata={},
        )
        fake_judge = FakeJudge(fixed_result=fixed_result)

        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def test(): pass",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python simples.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
            judge=fake_judge,
        )

        self.assertTrue(result.evaluation["passed"])
        stored = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertTrue(stored["passed"])

    def test_8_evaluator_preservado(self):
        """8. Evaluator string preservada."""
        fixed_result = JudgeResult(
            quality_score=0.5,
            passed=False,
            evaluator="custom_evaluator_v2",
            reason="test",
            criteria={},
            metadata={},
        )
        fake_judge = FakeJudge(fixed_result=fixed_result)

        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def test(): pass",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python simples.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
            judge=fake_judge,
        )

        self.assertEqual(result.evaluation["evaluator"], "custom_evaluator_v2")
        stored = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertEqual(stored["evaluator"], "custom_evaluator_v2")

    def test_9_criteria_preservado(self):
        """9. Criteria dict arbitrário preservado."""
        custom_criteria = {
            "correctness": 0.95,
            "completeness": 0.90,
            "style": 0.85,
            "custom_metric": 0.5,
        }
        fixed_result = JudgeResult(
            quality_score=0.8,
            passed=True,
            evaluator="fake",
            reason="test",
            criteria=custom_criteria,
            metadata={},
        )
        fake_judge = FakeJudge(fixed_result=fixed_result)

        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def test(): pass",
                latency_ms=500,
                cost=0.0,
                success=True,
                status="success",
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python simples.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
            judge=fake_judge,
        )

        self.assertEqual(result.evaluation["criteria"], custom_criteria)
        stored = self.repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertEqual(stored["criteria"], custom_criteria)

    def test_10_final_result_aggregation(self):
        """10. Resultado final agregado contém todos os campos."""
        router = FakeRoutingAdapter()
        router.set_execute_result(
            "openrouter/cohere/north-mini-code:free",
            RoutingExecutionResult(
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="openrouter/cohere/north-mini-code:free",
                provider="openrouter",
                output="def primes(n):\n    return [i for i in range(2, n+1) if all(i % j != 0 for j in range(2, int(i**0.5)+1))]",
                latency_ms=1000,
                cost=0.0,
                success=True,
                status="success",
                metadata={"correlation_id": "corr-final-123"},
            )
        )

        result = run_intelligence_loop(
            task_description="Escreva uma função Python que calcule os números primos até 100.",
            project_id=self.project_id,
            router=router,
            repo=self.repo,
        )

        # Verificar agregação completa
        self.assertIsNotNone(result.decision.get("decision_record_id"))
        self.assertIsNotNone(result.execution.get("execution_result_id"))
        self.assertIsNotNone(result.quality_evaluation_id)

        # Task info
        self.assertEqual(result.task, "Escreva uma função Python que calcule os números primos até 100.")
        self.assertEqual(result.task_type, "codigo")

        # Decision info
        self.assertEqual(result.decision["selected_model"], "openrouter/cohere/north-mini-code:free")
        self.assertGreater(result.decision["confidence"], 0.0)

        # Execution info
        self.assertEqual(result.execution["actual_model"], "openrouter/cohere/north-mini-code:free")
        self.assertEqual(result.execution["status"], "success")
        self.assertEqual(result.execution["correlation_id"], "corr-final-123")

        # Evaluation info
        self.assertGreaterEqual(result.evaluation["quality_score"], 0.0)
        self.assertLessEqual(result.evaluation["quality_score"], 1.0)
        self.assertEqual(result.evaluation["evaluator"], "rule_based")


class TestBuildJudgeContext(unittest.TestCase):
    """Testes da função build_judge_context."""

    def test_build_judge_context_all_fields(self):
        """build_judge_context popula todos os campos corretamente."""
        context = build_judge_context(
            task_id="task-123",
            task_type="codigo",
            task_description="Escreva código",
            decision_id="dec-456",
            decision_confidence=0.85,
            execution_result_id="exec-789",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="def test(): pass",
            execution_status="success",
            metadata={"correlation_id": "corr-123"},
        )

        self.assertIsInstance(context, JudgeContext)
        self.assertEqual(context.task_id, "task-123")
        self.assertEqual(context.task_type, "codigo")
        self.assertEqual(context.task_description, "Escreva código")
        self.assertEqual(context.decision_id, "dec-456")
        self.assertEqual(context.decision_confidence, 0.85)
        self.assertEqual(context.execution_result_id, "exec-789")
        self.assertEqual(context.requested_model, "model-a")
        self.assertEqual(context.actual_model, "model-a")
        self.assertEqual(context.provider, "provider-a")
        self.assertEqual(context.output, "def test(): pass")
        self.assertEqual(context.execution_status, "success")
        self.assertEqual(context.metadata["correlation_id"], "corr-123")


class TestBuildJudge(unittest.TestCase):
    """Testes da função build_judge."""

    def test_build_judge_default_policy(self):
        """build_judge cria RuleBasedJudge com policy padrão."""
        judge = build_judge()
        self.assertIsInstance(judge, RuleBasedJudge)
        self.assertEqual(judge.evaluator, "rule_based")

    def test_build_judge_custom_policy(self):
        """build_judge aceita policy customizada."""
        custom_policy = to_simple_policy(default_codigo_policy(threshold=0.8))
        judge = build_judge(policy=custom_policy)
        self.assertIsInstance(judge, RuleBasedJudge)


class TestIntelligenceLoopReal(unittest.TestCase):
    """Teste real opt-in com OmniRoute."""

    @unittest.skipUnless(
        os.getenv("RUN_REAL_OMNIROUTE") == "1",
        "Requer RUN_REAL_OMNIROUTE=1 e OmniRoute rodando em http://127.0.0.1:20128"
    )
    def test_real_omniroute_integration(self):
        """Teste real: OmniRoute → modelo → RuleBasedJudge → persistência."""
        task = "Escreva uma função Python que calcule os números primos até 100."

        repo = SQLiteDevRepository(":memory:")
        project_id = repo.criar_projeto(
            name="real-integration-test",
            description="Real integration test",
            product_type=None,
            complexity=None,
            status="active"
        )

        result = run_intelligence_loop_with_real_omniroute(
            task_description=task,
            project_id=project_id,
            repo=repo,
        )

        # Verificações do fluxo real
        self.assertEqual(result.task, task)
        self.assertEqual(result.task_type, "codigo")

        # Decision real
        self.assertIn("selected_model", result.decision)
        self.assertGreater(result.decision["confidence"], 0.0)
        self.assertIsNotNone(result.decision["decision_record_id"])

        # Execution real
        self.assertNotEqual(result.execution["actual_model"], "não executado")
        self.assertIn(result.execution["status"], ["success", "timeout", "provider_error", "billing_error", "unavailable", "rate_limited", "authentication_error", "malformed_response", "unknown_error"])
        self.assertIsNotNone(result.execution["execution_result_id"])

        # Evaluation real
        self.assertIsNotNone(result.evaluation["quality_score"])
        self.assertIsNotNone(result.evaluation["passed"])
        self.assertEqual(result.evaluation["evaluator"], "rule_based")
        self.assertIsNotNone(result.evaluation["reason"])
        self.assertIsNotNone(result.evaluation["criteria"])

        # Persistence real
        self.assertIsNotNone(result.quality_evaluation_id)

        # Verificar persistência no banco
        stored = repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["id"], result.quality_evaluation_id)
        self.assertEqual(stored["quality_score"], result.evaluation["quality_score"])
        self.assertEqual(stored["passed"], result.evaluation["passed"])
        self.assertEqual(stored["evaluator"], "rule_based")

        # DecisionRecord intacto
        decision = repo.obter_decisao(result.decision["decision_record_id"])
        self.assertIsNotNone(decision)
        self.assertEqual(decision["selected_model"], result.decision["selected_model"])

        # ExecutionResult intacto
        exec_result = repo.obter_execution_result(result.execution["execution_result_id"])
        self.assertIsNotNone(exec_result)
        self.assertEqual(exec_result["decision_record_id"], result.decision["decision_record_id"])

        # QualityEvaluation persistida
        quality_eval = repo.obter_quality_evaluation(result.quality_evaluation_id)
        self.assertIsNotNone(quality_eval)
        self.assertEqual(quality_eval["execution_result_id"], result.execution["execution_result_id"])

        print(f"✅ Real integration test passed")
        print(f"   Quality Score: {result.evaluation['quality_score']:.2f}")
        print(f"   Passed: {result.evaluation['passed']}")
        print(f"   Evaluator: {result.evaluation['evaluator']}")
        print(f"   Criteria: {result.evaluation['criteria']}")


if __name__ == "__main__":
    unittest.main()