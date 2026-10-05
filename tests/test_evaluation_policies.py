"""Testes das Evaluation Policies — PATCH 005C.

Valida políticas de avaliação por domínio:
- CODIGO
- TEXTO
- ARQUITETURA

Zero dependências externas, zero chamadas de rede/LLM.
"""

import unittest
from olympus.judge.policies import (
    TASK_TYPE_CODIGO,
    TASK_TYPE_TEXTO,
    TASK_TYPE_ARQUITETURA,
    CODIGO_CRITERIA,
    TEXTO_CRITERIA,
    ARQUITETURA_CRITERIA,
    CODIGO_DEFAULT_THRESHOLD,
    TEXTO_DEFAULT_THRESHOLD,
    ARQUITETURA_DEFAULT_THRESHOLD,
    DomainEvaluationPolicy,
    default_codigo_policy,
    default_texto_policy,
    default_arquitetura_policy,
    to_simple_policy,
)
from olympus.judge.interfaces import SimpleEvaluationPolicy


class TestPolicyConstants(unittest.TestCase):
    """Testes das constantes de domínio."""

    def test_1_task_type_constants(self):
        """1. Constantes de task_type definidas."""
        self.assertEqual(TASK_TYPE_CODIGO, "codigo")
        self.assertEqual(TASK_TYPE_TEXTO, "texto")
        self.assertEqual(TASK_TYPE_ARQUITETURA, "arquitetura")

    def test_2_criteria_constants(self):
        """2. Critérios canônicos por domínio."""
        self.assertEqual(CODIGO_CRITERIA, {
            "non_empty_output": 1.0,
            "minimum_content": 1.0,
            "expected_structure": 1.0,
        })
        self.assertEqual(TEXTO_CRITERIA, {
            "non_empty_output": 1.0,
            "minimum_content": 1.0,
        })
        self.assertEqual(ARQUITETURA_CRITERIA, {
            "non_empty_output": 1.0,
            "minimum_content": 1.0,
            "structural_completeness": 1.0,
        })

    def test_3_threshold_constants(self):
        """3. Thresholds padrão por domínio."""
        self.assertEqual(CODIGO_DEFAULT_THRESHOLD, 0.6)
        self.assertEqual(TEXTO_DEFAULT_THRESHOLD, 0.5)
        self.assertEqual(ARQUITETURA_DEFAULT_THRESHOLD, 0.6)


class TestDomainEvaluationPolicy(unittest.TestCase):
    """Testes da classe DomainEvaluationPolicy."""

    def test_4_codigo_policy_construction(self):
        """4. Construção de policy CODIGO."""
        policy = DomainEvaluationPolicy(
            task_type=TASK_TYPE_CODIGO,
            minimum_quality_score=CODIGO_DEFAULT_THRESHOLD,
            criteria=dict(CODIGO_CRITERIA),
        )
        self.assertEqual(policy.task_type, "codigo")
        self.assertEqual(policy.minimum_quality_score, 0.6)
        self.assertEqual(policy.criteria, CODIGO_CRITERIA)
        self.assertEqual(policy.pass_threshold, 0.6)

    def test_5_texto_policy_construction(self):
        """5. Construção de policy TEXTO."""
        policy = DomainEvaluationPolicy(
            task_type=TASK_TYPE_TEXTO,
            minimum_quality_score=TEXTO_DEFAULT_THRESHOLD,
            criteria=dict(TEXTO_CRITERIA),
        )
        self.assertEqual(policy.task_type, "texto")
        self.assertEqual(policy.minimum_quality_score, 0.5)
        self.assertEqual(policy.criteria, TEXTO_CRITERIA)
        self.assertEqual(policy.pass_threshold, 0.5)

    def test_6_arquitetura_policy_construction(self):
        """6. Construção de policy ARQUITETURA."""
        policy = DomainEvaluationPolicy(
            task_type=TASK_TYPE_ARQUITETURA,
            minimum_quality_score=ARQUITETURA_DEFAULT_THRESHOLD,
            criteria=dict(ARQUITETURA_CRITERIA),
        )
        self.assertEqual(policy.task_type, "arquitetura")
        self.assertEqual(policy.minimum_quality_score, 0.6)
        self.assertEqual(policy.criteria, ARQUITETURA_CRITERIA)
        self.assertEqual(policy.pass_threshold, 0.6)

    def test_7_criteria_correct(self):
        """7. Critérios corretos por domínio."""
        codigo = DomainEvaluationPolicy(
            task_type=TASK_TYPE_CODIGO,
            minimum_quality_score=0.6,
            criteria=dict(CODIGO_CRITERIA),
        )
        self.assertIn("expected_structure", codigo.criteria)
        self.assertNotIn("structural_completeness", codigo.criteria)

        texto = DomainEvaluationPolicy(
            task_type=TASK_TYPE_TEXTO,
            minimum_quality_score=0.5,
            criteria=dict(TEXTO_CRITERIA),
        )
        self.assertNotIn("expected_structure", texto.criteria)
        self.assertNotIn("structural_completeness", texto.criteria)

        arquitetura = DomainEvaluationPolicy(
            task_type=TASK_TYPE_ARQUITETURA,
            minimum_quality_score=0.6,
            criteria=dict(ARQUITETURA_CRITERIA),
        )
        self.assertIn("structural_completeness", arquitetura.criteria)
        self.assertNotIn("expected_structure", arquitetura.criteria)

    def test_8_thresholds(self):
        """8. Thresholds definidos e válidos."""
        for threshold in [0.0, 0.3, 0.5, 0.7, 1.0]:
            policy = DomainEvaluationPolicy(
                task_type="codigo",
                minimum_quality_score=threshold,
                criteria={},
            )
            self.assertEqual(policy.pass_threshold, threshold)

    def test_9_metadata(self):
        """9. Metadata preservado."""
        metadata = {"version": "1.0", "author": "test"}
        policy = DomainEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria={},
            metadata=metadata,
        )
        self.assertEqual(policy.metadata, metadata)

    def test_10_immutability(self):
        """10. Policy é imutável (frozen dataclass)."""
        policy = DomainEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria={},
        )
        with self.assertRaises(Exception):
            policy.task_type = "other"
        with self.assertRaises(Exception):
            policy.minimum_quality_score = 0.9

    def test_11_independence_between_instances(self):
        """11. Instâncias independentes (deep copy implícito)."""
        p1 = DomainEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria=dict(CODIGO_CRITERIA),
        )
        p2 = DomainEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria=dict(CODIGO_CRITERIA),
        )
        self.assertIsNot(p1.criteria, p2.criteria)
        p1.criteria["non_empty_output"] = 0.0
        self.assertEqual(p2.criteria["non_empty_output"], 1.0)

    def test_12_weights_in_metadata(self):
        """12. Pesos suportados via metadata."""
        weights = {"expected_structure": 2.0, "non_empty_output": 1.0}
        policy = DomainEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria=dict(CODIGO_CRITERIA),
            metadata={"weights": weights},
        )
        self.assertEqual(policy.metadata["weights"], weights)

    def test_13_policy_does_not_calculate_score(self):
        """13. Policy NÃO calcula quality_score — apenas declara critérios/threshold."""
        policy = default_codigo_policy()
        # Policy não tem método evaluate, score, compute, etc.
        self.assertFalse(hasattr(policy, "evaluate"))
        self.assertFalse(hasattr(policy, "calculate_score"))
        self.assertFalse(hasattr(policy, "compute"))

    def test_14_policy_no_judge_dependency(self):
        """14. Policy não depende de Judge."""
        import olympus.judge.policies as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RuleBasedJudge", source)
        self.assertNotIn("JudgeAdapter", source)
        # Import de interfaces só para SimpleEvaluationPolicy no helper
        self.assertIn("from olympus.judge.interfaces import SimpleEvaluationPolicy", source)

    def test_15_policy_no_omniroute_dependency(self):
        """15. Policy não depende de OmniRoute."""
        import olympus.judge.policies as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("OmniRoute", source)
        self.assertNotIn("omniroute", source.lower())

    def test_16_policy_no_routing_adapter_dependency(self):
        """16. Policy não depende de RoutingAdapter."""
        import olympus.judge.policies as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RoutingAdapter", source)
        self.assertNotIn("OmniRouteAdapter", source)

    def test_17_python39_compatibility(self):
        """17. Python 3.9 compatibility — Optional[Dict] em vez de Dict | None."""
        import olympus.judge.policies as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        # Verifica uso de Optional (Python 3.9 compatible)
        self.assertIn("Optional", source)
        # Não usa union syntax Python 3.10+
        self.assertNotIn("Dict | None", source)
        self.assertNotIn("list | None", source)

    def test_18_default_factories(self):
        """18. Factories padrão retornam políticas imutáveis."""
        p1 = default_codigo_policy()
        p2 = default_texto_policy()
        p3 = default_arquitetura_policy()

        self.assertEqual(p1.task_type, "codigo")
        self.assertEqual(p1.minimum_quality_score, 0.6)
        self.assertEqual(p2.task_type, "texto")
        self.assertEqual(p2.minimum_quality_score, 0.5)
        self.assertEqual(p3.task_type, "arquitetura")
        self.assertEqual(p3.minimum_quality_score, 0.6)

    def test_19_factory_with_custom_threshold(self):
        """19. Factory aceita threshold customizado."""
        p = default_codigo_policy(threshold=0.8)
        self.assertEqual(p.minimum_quality_score, 0.8)

    def test_20_factory_with_custom_weights(self):
        """20. Factory aceita pesos customizados."""
        weights = {"expected_structure": 3.0, "non_empty_output": 1.0, "minimum_content": 1.0}
        p = default_codigo_policy(weights=weights)
        self.assertEqual(p.metadata["weights"], weights)

    def test_21_factory_with_additional_metadata(self):
        """21. Factory aceita metadata adicional."""
        p = default_codigo_policy(metadata={"version": "2.0", "env": "test"})
        self.assertEqual(p.metadata["version"], "2.0")
        self.assertEqual(p.metadata["env"], "test")

    def test_22_factory_weights_merged_with_metadata(self):
        """22. Weights são mesclados com metadata."""
        p = default_codigo_policy(
            weights={"expected_structure": 2.0},
            metadata={"version": "1.0"},
        )
        self.assertEqual(p.metadata["weights"]["expected_structure"], 2.0)
        self.assertEqual(p.metadata["version"], "1.0")

    def test_23_criteria_extensible(self):
        """23. Critérios são extensíveis (dict)."""
        custom_criteria = {
            "non_empty_output": 1.0,
            "minimum_content": 1.0,
            "expected_structure": 1.0,
            "custom_metric": 0.8,  # critério extra — não usado por RuleBasedJudge mas permitido
        }
        policy = DomainEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria=custom_criteria,
        )
        self.assertIn("custom_metric", policy.criteria)

    def test_24_no_semantic_criteria_without_evaluator(self):
        """24. Critérios semânticos (correctness, security, etc.) NÃO incluídos por padrão."""
        p_codigo = default_codigo_policy()
        self.assertNotIn("algorithm_correctness", p_codigo.criteria)
        self.assertNotIn("security", p_codigo.criteria)
        self.assertNotIn("performance", p_codigo.criteria)
        self.assertNotIn("tests_passed", p_codigo.criteria)

        p_texto = default_texto_policy()
        self.assertNotIn("semantic_accuracy", p_texto.criteria)
        self.assertNotIn("factual_correctness", p_texto.criteria)

        p_arq = default_arquitetura_policy()
        self.assertNotIn("architectural_soundness", p_arq.criteria)
        self.assertNotIn("scalability", p_arq.criteria)


class TestToSimplePolicy(unittest.TestCase):
    """Testes do helper to_simple_policy."""

    def test_25_to_simple_policy_conversion(self):
        """25. Conversão para SimpleEvaluationPolicy preserva dados."""
        domain_policy = default_codigo_policy(
            threshold=0.7,
            weights={"expected_structure": 2.0},
            metadata={"version": "1.0"},
        )
        simple = to_simple_policy(domain_policy)

        self.assertIsInstance(simple, SimpleEvaluationPolicy)
        self.assertEqual(simple.task_type, "codigo")
        self.assertEqual(simple.minimum_quality_score, 0.7)
        self.assertEqual(simple.criteria, CODIGO_CRITERIA)
        self.assertEqual(simple.metadata["weights"]["expected_structure"], 2.0)
        self.assertEqual(simple.metadata["version"], "1.0")

    def test_26_simple_policy_compatible_with_judge(self):
        """26. SimpleEvaluationPolicy resultante compatível com RuleBasedJudge."""
        from olympus.judge.rule_based import RuleBasedJudge
        from olympus.judge.interfaces import JudgeContext

        domain_policy = default_codigo_policy()
        simple = to_simple_policy(domain_policy)
        judge = RuleBasedJudge(policy=simple)

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
            output="def hello(): pass",
            execution_status="success",
        )
        result = judge.evaluate(ctx)
        self.assertIsInstance(result.quality_score, float)
        self.assertIn("non_empty_output", result.criteria)


class TestPolicyIntegration(unittest.TestCase):
    """Testes de integração básica com RuleBasedJudge."""

    def test_27_codigo_policy_with_judge(self):
        """27. CODIGO policy funciona com RuleBasedJudge."""
        from olympus.judge.rule_based import RuleBasedJudge
        from olympus.judge.interfaces import JudgeContext

        policy = default_codigo_policy()
        judge = RuleBasedJudge(policy=to_simple_policy(policy))

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
            output="def hello(): pass",
            execution_status="success",
        )
        result = judge.evaluate(ctx)
        self.assertTrue(result.passed)
        self.assertEqual(result.quality_score, 1.0)

    def test_28_texto_policy_with_judge(self):
        """28. TEXTO policy funciona com RuleBasedJudge."""
        from olympus.judge.rule_based import RuleBasedJudge
        from olympus.judge.interfaces import JudgeContext

        policy = default_texto_policy()
        judge = RuleBasedJudge(policy=to_simple_policy(policy))

        ctx = JudgeContext(
            task_id="task-1",
            task_type="texto",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="Este é um texto longo o suficiente para passar no mínimo.",
            execution_status="success",
        )
        result = judge.evaluate(ctx)
        self.assertTrue(result.passed)
        self.assertIn("structural_completeness", result.criteria)

    def test_29_arquitetura_policy_with_judge(self):
        """29. ARQUITETURA policy funciona com RuleBasedJudge."""
        from olympus.judge.rule_based import RuleBasedJudge
        from olympus.judge.interfaces import JudgeContext

        policy = default_arquitetura_policy()
        judge = RuleBasedJudge(policy=to_simple_policy(policy))

        ctx = JudgeContext(
            task_id="task-1",
            task_type="arquitetura",
            task_description="Test",
            decision_id="dec-1",
            decision_confidence=0.9,
            execution_result_id="exec-1",
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="Arquitetura proposta: microserviços com API Gateway e event-driven communication.",
            execution_status="success",
        )
        result = judge.evaluate(ctx)
        self.assertTrue(result.passed)
        self.assertIn("structural_completeness", result.criteria)


if __name__ == "__main__":
    unittest.main()