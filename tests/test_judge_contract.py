"""Testes do Judge Contract — PATCH 005A.

Valida contratos: JudgeContext, JudgeResult, JudgeAdapter, EvaluationPolicy.
Zero dependências externas, zero chamadas de rede/LLM.
"""

import unittest
from olympus.judge.interfaces import (
    JudgeContext,
    JudgeResult,
    JudgeAdapter,
    EvaluationPolicy,
    SimpleEvaluationPolicy,
    FakeJudge,
)


class TestJudgeContext(unittest.TestCase):
    """Testes de JudgeContext construction e imutabilidade."""

    def test_1_context_construction(self):
        """1. JudgeContext construction com todos os campos."""
        ctx = JudgeContext(
            task_id="task-123",
            task_type="codigo",
            task_description="Escreva uma função Python",
            decision_id="dec-456",
            decision_confidence=0.85,
            execution_result_id="exec-789",
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="def hello(): pass",
            execution_status="success",
            metadata={"correlation_id": "corr-123"},
        )
        self.assertEqual(ctx.task_id, "task-123")
        self.assertEqual(ctx.task_type, "codigo")
        self.assertEqual(ctx.task_description, "Escreva uma função Python")
        self.assertEqual(ctx.decision_id, "dec-456")
        self.assertEqual(ctx.decision_confidence, 0.85)
        self.assertEqual(ctx.execution_result_id, "exec-789")
        self.assertEqual(ctx.requested_model, "openrouter/cohere/north-mini-code:free")
        self.assertEqual(ctx.actual_model, "cohere/north-mini-code:free")
        self.assertEqual(ctx.provider, "cohere")
        self.assertEqual(ctx.output, "def hello(): pass")
        self.assertEqual(ctx.execution_status, "success")
        self.assertEqual(ctx.metadata, {"correlation_id": "corr-123"})

    def test_2_context_minimal_metadata_default(self):
        """2. metadata defaulta para dict vazio quando None."""
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="output",
            execution_status="success",
            metadata=None,
        )
        self.assertEqual(ctx.metadata, {})

    def test_3_context_frozen_immutable(self):
        """3. JudgeContext é frozen (imutável)."""
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="output",
            execution_status="success",
        )
        with self.assertRaises(Exception):
            ctx.task_id = "other"

    def test_4_context_requested_model_different_actual_model(self):
        """13. requested_model != actual_model permitido."""
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="openrouter/nvidia/nemotron-3.5-lightning:free",
            provider="nvidia",
            output="output",
            execution_status="success",
        )
        self.assertNotEqual(ctx.requested_model, ctx.actual_model)


class TestJudgeResult(unittest.TestCase):
    """Testes de JudgeResult construction, validação e imutabilidade."""

    def test_5_quality_score_zero(self):
        """4. quality_score = 0 válido."""
        result = JudgeResult(
            quality_score=0.0,
            passed=False,
            evaluator="rule_based",
            reason="completely incorrect",
            criteria={"correctness": 0.0},
        )
        self.assertEqual(result.quality_score, 0.0)
        self.assertFalse(result.passed)

    def test_6_quality_score_one(self):
        """5. quality_score = 1 válido."""
        result = JudgeResult(
            quality_score=1.0,
            passed=True,
            evaluator="rule_based",
            reason="perfect",
            criteria={"correctness": 1.0},
        )
        self.assertEqual(result.quality_score, 1.0)
        self.assertTrue(result.passed)

    def test_7_quality_score_intermediate(self):
        """6. quality_score intermediário válido."""
        result = JudgeResult(
            quality_score=0.75,
            passed=True,
            evaluator="code",
            reason="mostly correct",
            criteria={"correctness": 0.8, "style": 0.7},
        )
        self.assertEqual(result.quality_score, 0.75)
        self.assertTrue(result.passed)

    def test_8_quality_score_invalid_negative(self):
        """7. quality_score < 0 falha deterministicamente."""
        with self.assertRaises(ValueError) as cm:
            JudgeResult(
                quality_score=-0.1,
                passed=False,
                evaluator="test",
                reason="test",
                criteria={},
            )
        self.assertIn("quality_score must be in [0.0, 1.0]", str(cm.exception))

    def test_9_quality_score_invalid_above_one(self):
        """7. quality_score > 1 falha deterministicamente."""
        with self.assertRaises(ValueError) as cm:
            JudgeResult(
                quality_score=1.1,
                passed=True,
                evaluator="test",
                reason="test",
                criteria={},
            )
        self.assertIn("quality_score must be in [0.0, 1.0]", str(cm.exception))

    def test_10_result_frozen_immutable(self):
        """JudgeResult é frozen (imutável)."""
        result = JudgeResult(
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
            criteria={},
        )
        with self.assertRaises(Exception):
            result.quality_score = 0.9

    def test_11_evaluator_extensible(self):
        """10. evaluator é string extensível (não enum fechado)."""
        for evaluator in ["rule_based", "code", "text", "architecture", "llm", "human", "composite", "custom_xyz"]:
            result = JudgeResult(
                quality_score=0.5,
                passed=False,
                evaluator=evaluator,
                reason="test",
                criteria={},
            )
            self.assertEqual(result.evaluator, evaluator)

    def test_12_criteria_arbitrary(self):
        """11. criteria aceita dict arbitrário."""
        criteria = {
            "correctness": 0.95,
            "completeness": 0.90,
            "relevance": 1.0,
            "custom_metric": 0.5,
        }
        result = JudgeResult(
            quality_score=0.85,
            passed=True,
            evaluator="code",
            reason="good",
            criteria=criteria,
        )
        self.assertEqual(result.criteria, criteria)

    def test_13_metadata_arbitrary(self):
        """12. metadata aceita dict arbitrário."""
        metadata = {"evaluator_version": "1.0", "duration_ms": 150}
        result = JudgeResult(
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
            criteria={},
            metadata=metadata,
        )
        self.assertEqual(result.metadata, metadata)

    def test_14_execution_status_preserved(self):
        """14. execution_status preservado no context, não misturado."""
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="output",
            execution_status="timeout",  # diferente de success
        )
        result = JudgeResult(
            quality_score=0.0,
            passed=False,
            evaluator="test",
            reason="execution failed",
            criteria={},
        )
        self.assertEqual(ctx.execution_status, "timeout")
        self.assertFalse(result.passed)


class TestJudgeAdapter(unittest.TestCase):
    """Testes de JudgeAdapter protocol e implementations."""

    def test_15_fake_judge_satisfies_protocol(self):
        """8. FakeJudge satisfaz JudgeAdapter (protocol compliance)."""
        judge = FakeJudge()
        self.assertIsInstance(judge, JudgeAdapter)

    def test_16_evaluate_returns_judge_result(self):
        """9. evaluate retorna JudgeResult."""
        judge = FakeJudge()
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="output",
            execution_status="success",
        )
        result = judge.evaluate(ctx)
        self.assertIsInstance(result, JudgeResult)
        self.assertEqual(result.evaluator, "fake")
        self.assertEqual(result.quality_score, 0.8)
        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "fake evaluation")

    def test_17_evaluate_with_fixed_result(self):
        """9. evaluate retorna resultado fixo quando configurado."""
        fixed = JudgeResult(
            quality_score=0.3,
            passed=False,
            evaluator="fixed",
            reason="fixed reason",
            criteria={"fixed": 0.3},
        )
        judge = FakeJudge(fixed_result=fixed)
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="output",
            execution_status="success",
        )
        result = judge.evaluate(ctx)
        self.assertEqual(result.quality_score, 0.3)
        self.assertEqual(result.evaluator, "fixed")
        self.assertFalse(result.passed)

    def test_18_no_omniroute_dependency(self):
        """15. JudgeAdapter não depende de OmniRoute."""
        import olympus.judge.interfaces as judge_module
        source = __import__("pathlib").Path(judge_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("OmniRoute", source)
        self.assertNotIn("omniroute", source.lower())

    def test_19_no_routing_adapter_dependency(self):
        """16. JudgeAdapter não depende de RoutingAdapter concreto."""
        import olympus.judge.interfaces as judge_module
        source = __import__("pathlib").Path(judge_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RoutingAdapter", source)
        self.assertNotIn("OmniRouteAdapter", source)


class TestEvaluationPolicy(unittest.TestCase):
    """Testes de EvaluationPolicy."""

    def test_20_policy_construction(self):
        """17. SimpleEvaluationPolicy construction."""
        policy = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.75,
            criteria={"correctness": 0.8, "completeness": 0.7},
            metadata={"version": "1.0"},
        )
        self.assertEqual(policy.task_type, "codigo")
        self.assertEqual(policy.minimum_quality_score, 0.75)
        self.assertEqual(policy.criteria, {"correctness": 0.8, "completeness": 0.7})
        self.assertEqual(policy.metadata, {"version": "1.0"})

    def test_21_policy_threshold_preservation(self):
        """18. pass_threshold preservado."""
        policy = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.85,
        )
        self.assertEqual(policy.pass_threshold, 0.85)
        self.assertEqual(policy.minimum_quality_score, 0.85)

    def test_22_policy_criteria_preservation(self):
        """19. criteria preservado."""
        criteria = {"correctness": 0.9, "style": 0.8}
        policy = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.7,
            criteria=criteria,
        )
        self.assertEqual(policy.criteria, criteria)

    def test_23_policy_invalid_threshold_negative(self):
        """minimum_quality_score < 0 falha."""
        with self.assertRaises(ValueError) as cm:
            SimpleEvaluationPolicy(
                task_type="codigo",
                minimum_quality_score=-0.1,
            )
        self.assertIn("minimum_quality_score must be in [0.0, 1.0]", str(cm.exception))

    def test_24_policy_invalid_threshold_above_one(self):
        """minimum_quality_score > 1 falha."""
        with self.assertRaises(ValueError) as cm:
            SimpleEvaluationPolicy(
                task_type="codigo",
                minimum_quality_score=1.1,
            )
        self.assertIn("minimum_quality_score must be in [0.0, 1.0]", str(cm.exception))

    def test_25_policy_defaults_empty_dicts(self):
        """criteria e metadata defaultam para dict vazio."""
        policy = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.5,
            criteria=None,
            metadata=None,
        )
        self.assertEqual(policy.criteria, {})
        self.assertEqual(policy.metadata, {})


class TestConceptSeparation(unittest.TestCase):
    """Testes garantindo separação de conceitos obrigatória."""

    def test_decision_confidence_vs_quality_score(self):
        """Decision Confidence ≠ Quality Score."""
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.95,  # alta confiança na decisão
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="wrong output",
            execution_status="success",
        )
        # Quality score pode ser baixo mesmo com alta decision confidence
        result = JudgeResult(
            quality_score=0.2,  # baixa qualidade
            passed=False,
            evaluator="code",
            reason="incorrect output",
            criteria={"correctness": 0.2},
        )
        self.assertNotEqual(ctx.decision_confidence, result.quality_score)
        self.assertGreater(ctx.decision_confidence, result.quality_score)

    def test_execution_status_vs_quality_score(self):
        """ExecutionStatus ≠ Quality Score."""
        # Execução técnica bem-sucedida mas qualidade baixa
        ctx = JudgeContext(
            task_id="task-1",
            task_type="codigo",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="print('hello')",  # não responde à tarefa
            execution_status="success",  # execução OK
        )
        result = JudgeResult(
            quality_score=0.1,
            passed=False,
            evaluator="code",
            reason="irrelevant output",
            criteria={"relevance": 0.1},
        )
        self.assertEqual(ctx.execution_status, "success")
        self.assertFalse(result.passed)
        self.assertLess(result.quality_score, 0.5)

    def test_final_confidence_not_created(self):
        """Final Confidence NÃO criado neste patch."""
        # JudgeResult NÃO tem campo final_confidence
        result = JudgeResult(
            quality_score=0.8,
            passed=True,
            evaluator="test",
            reason="test",
            criteria={},
        )
        self.assertFalse(hasattr(result, "final_confidence"))


if __name__ == "__main__":
    unittest.main()