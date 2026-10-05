"""Testes do Final Confidence Policy — PATCH 005F.

Valida:
- score boundaries (0.0, 1.0, intermediate)
- technical failure → reselect
- deliver action (>= 0.80)
- review action (>= 0.60, < 0.80)
- reselect action (< 0.60)
- configurable weights
- configurable thresholds
- invalid configuration
- determinism
- immutability
- reason string populated
- metadata populated
- DecisionConfidence != QualityScore != FinalConfidence
"""

import copy
import unittest

from olympus.judge.final_confidence import (
    FinalConfidenceConfig,
    FinalConfidenceResult,
    FinalConfidenceCalculator,
    compute_final_confidence,
    ACTION_DELIVER,
    ACTION_REVIEW,
    ACTION_RESELECT,
    DEFAULT_QUALITY_WEIGHT,
    DEFAULT_DECISION_WEIGHT,
    DEFAULT_DELIVER_THRESHOLD,
    DEFAULT_REVIEW_THRESHOLD,
)


class TestFinalConfidenceConfig(unittest.TestCase):
    """Testes de configuração e validação."""

    def test_1_default_config(self):
        """1. Configuração padrão válida."""
        config = FinalConfidenceConfig()
        self.assertEqual(config.quality_weight, DEFAULT_QUALITY_WEIGHT)
        self.assertEqual(config.decision_weight, DEFAULT_DECISION_WEIGHT)
        self.assertEqual(config.deliver_threshold, DEFAULT_DELIVER_THRESHOLD)
        self.assertEqual(config.review_threshold, DEFAULT_REVIEW_THRESHOLD)
        self.assertAlmostEqual(config.weights_sum, 1.0)

    def test_2_custom_valid_config(self):
        """2. Configuração customizada válida."""
        config = FinalConfidenceConfig(
            quality_weight=0.6,
            decision_weight=0.4,
            deliver_threshold=0.75,
            review_threshold=0.55,
        )
        self.assertEqual(config.quality_weight, 0.6)
        self.assertEqual(config.decision_weight, 0.4)
        self.assertEqual(config.deliver_threshold, 0.75)
        self.assertEqual(config.review_threshold, 0.55)

    def test_3_invalid_quality_weight_negative(self):
        """3. quality_weight < 0 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(quality_weight=-0.1, decision_weight=1.1)
        self.assertIn("quality_weight must be in [0.0, 1.0]", str(cm.exception))

    def test_4_invalid_quality_weight_above_one(self):
        """4. quality_weight > 1 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(quality_weight=1.1, decision_weight=-0.1)
        self.assertIn("quality_weight must be in [0.0, 1.0]", str(cm.exception))

    def test_5_invalid_decision_weight_negative(self):
        """5. decision_weight < 0 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(quality_weight=0.5, decision_weight=-0.1)
        self.assertIn("decision_weight must be in [0.0, 1.0]", str(cm.exception))

    def test_6_invalid_decision_weight_above_one(self):
        """6. decision_weight > 1 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(quality_weight=0.5, decision_weight=1.1)
        self.assertIn("decision_weight must be in [0.0, 1.0]", str(cm.exception))

    def test_7_weights_dont_sum_to_one(self):
        """7. Pesos que não somam 1.0 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(quality_weight=0.5, decision_weight=0.3)
        self.assertIn("weights must sum to 1.0", str(cm.exception))

    def test_8_invalid_deliver_threshold_negative(self):
        """8. deliver_threshold < 0 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(deliver_threshold=-0.1)
        self.assertIn("deliver_threshold must be in [0.0, 1.0]", str(cm.exception))

    def test_9_invalid_deliver_threshold_above_one(self):
        """9. deliver_threshold > 1 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(deliver_threshold=1.1)
        self.assertIn("deliver_threshold must be in [0.0, 1.0]", str(cm.exception))

    def test_10_invalid_review_threshold_negative(self):
        """10. review_threshold < 0 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(review_threshold=-0.1)
        self.assertIn("review_threshold must be in [0.0, 1.0]", str(cm.exception))

    def test_11_invalid_review_threshold_above_one(self):
        """11. review_threshold > 1 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(review_threshold=1.1)
        self.assertIn("review_threshold must be in [0.0, 1.0]", str(cm.exception))

    def test_12_review_threshold_not_less_than_deliver(self):
        """12. review_threshold >= deliver_threshold falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceConfig(deliver_threshold=0.7, review_threshold=0.8)
        self.assertIn("review_threshold", str(cm.exception))
        self.assertIn("deliver_threshold", str(cm.exception))

    def test_13_config_immutable(self):
        """13. FinalConfidenceConfig é frozen (imutável)."""
        config = FinalConfidenceConfig()
        with self.assertRaises(Exception):
            config.quality_weight = 0.9


class TestFinalConfidenceResult(unittest.TestCase):
    """Testes de FinalConfidenceResult construction e validação."""

    def test_14_result_construction(self):
        """14. FinalConfidenceResult construction válido."""
        result = FinalConfidenceResult(
            confidence=0.85,
            action=ACTION_DELIVER,
            reason="High confidence",
            metadata={"test": "data"},
        )
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.action, ACTION_DELIVER)
        self.assertEqual(result.reason, "High confidence")
        self.assertEqual(result.metadata, {"test": "data"})

    def test_15_confidence_zero_valid(self):
        """15. confidence = 0 válido."""
        result = FinalConfidenceResult(
            confidence=0.0,
            action=ACTION_RESELECT,
            reason="Zero confidence",
            metadata={},
        )
        self.assertEqual(result.confidence, 0.0)

    def test_16_confidence_one_valid(self):
        """16. confidence = 1 válido."""
        result = FinalConfidenceResult(
            confidence=1.0,
            action=ACTION_DELIVER,
            reason="Perfect",
            metadata={},
        )
        self.assertEqual(result.confidence, 1.0)

    def test_17_confidence_negative_invalid(self):
        """17. confidence < 0 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceResult(
                confidence=-0.1,
                action=ACTION_DELIVER,
                reason="test",
                metadata={},
            )
        self.assertIn("confidence must be in [0.0, 1.0]", str(cm.exception))

    def test_18_confidence_above_one_invalid(self):
        """18. confidence > 1 falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceResult(
                confidence=1.1,
                action=ACTION_DELIVER,
                reason="test",
                metadata={},
            )
        self.assertIn("confidence must be in [0.0, 1.0]", str(cm.exception))

    def test_19_invalid_action(self):
        """19. action inválido falha."""
        with self.assertRaises(ValueError) as cm:
            FinalConfidenceResult(
                confidence=0.5,
                action="invalid_action",
                reason="test",
                metadata={},
            )
        self.assertIn("action must be one of", str(cm.exception))

    def test_20_result_immutable(self):
        """20. FinalConfidenceResult é frozen (imutável)."""
        result = FinalConfidenceResult(
            confidence=0.5,
            action=ACTION_REVIEW,
            reason="test",
            metadata={},
        )
        with self.assertRaises(Exception):
            result.confidence = 0.9


class TestFinalConfidenceCalculator(unittest.TestCase):
    """Testes do calculador principal."""

    def setUp(self):
        self.calculator = FinalConfidenceCalculator()

    def test_21_technical_failure_returns_reselect(self):
        """21. Falha técnica → action=reselect, confidence=0."""
        result = self.calculator.compute(
            decision_confidence=0.9,
            quality_score=0.9,
            execution_status="timeout",
        )
        self.assertEqual(result.action, ACTION_RESELECT)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("did not succeed", result.reason)
        self.assertTrue(result.metadata.get("technical_failure"))

    def test_22_various_failure_statuses(self):
        """22. Vários status de falha técnica → reselect."""
        failure_statuses = [
            "timeout",
            "provider_error",
            "billing_error",
            "unavailable",
            "rate_limited",
            "authentication_error",
            "malformed_response",
            "unknown_error",
        ]
        for status in failure_statuses:
            with self.subTest(status=status):
                result = self.calculator.compute(
                    decision_confidence=0.8,
                    quality_score=0.8,
                    execution_status=status,
                )
                self.assertEqual(result.action, ACTION_RESELECT)
                self.assertEqual(result.confidence, 0.0)

    def test_23_technical_failure_metadata_preserves_inputs(self):
        """23. Falha técnica preserva inputs no metadata."""
        result = self.calculator.compute(
            decision_confidence=0.75,
            quality_score=0.85,
            execution_status="provider_error",
        )
        self.assertEqual(result.metadata["decision_confidence"], 0.75)
        self.assertEqual(result.metadata["quality_score"], 0.85)
        self.assertEqual(result.metadata["execution_status"], "provider_error")

    def test_24_success_computes_weighted_confidence(self):
        """24. Sucesso técnico → confidence = weighted sum."""
        # quality=1.0, decision=1.0, weights 0.7/0.3 → 1.0
        result = self.calculator.compute(
            decision_confidence=1.0,
            quality_score=1.0,
            execution_status="success",
        )
        self.assertEqual(result.confidence, 1.0)

    def test_25_weighted_confidence_formula(self):
        """25. Fórmula: quality*0.7 + decision*0.3."""
        # quality=0.8, decision=0.4 → 0.8*0.7 + 0.4*0.3 = 0.56 + 0.12 = 0.68
        result = self.calculator.compute(
            decision_confidence=0.4,
            quality_score=0.8,
            execution_status="success",
        )
        self.assertAlmostEqual(result.confidence, 0.68, places=5)

    def test_26_not_simple_multiplication(self):
        """26. NÃO é multiplicação simples (quality * decision)."""
        # Se fosse multiplicação: 0.5 * 0.5 = 0.25
        # Peso 0.7/0.3: 0.5*0.7 + 0.5*0.3 = 0.5
        result = self.calculator.compute(
            decision_confidence=0.5,
            quality_score=0.5,
            execution_status="success",
        )
        self.assertEqual(result.confidence, 0.5)
        self.assertNotEqual(result.confidence, 0.25)  # não é multiplicação

    def test_27_quality_has_greater_weight_default(self):
        """27. Default: quality weight (0.70) > decision weight (0.30)."""
        config = self.calculator.config
        self.assertGreater(config.quality_weight, config.decision_weight)

    def test_28_deliver_threshold_boundary(self):
        """28. confidence >= 0.80 → deliver."""
        result = self.calculator.compute(
            decision_confidence=1.0,
            quality_score=0.80,
            execution_status="success",
        )
        self.assertEqual(result.action, ACTION_DELIVER)
        self.assertTrue(result.confidence >= DEFAULT_DELIVER_THRESHOLD)

    def test_29_deliver_above_threshold(self):
        """29. confidence > 0.80 → deliver."""
        result = self.calculator.compute(
            decision_confidence=1.0,
            quality_score=0.9,
            execution_status="success",
        )
        self.assertEqual(result.action, ACTION_DELIVER)

    def test_30_review_threshold_boundary(self):
        """30. 0.60 <= confidence < 0.80 → review."""
        # Need quality=0.60, decision=0.60 → 0.60*0.7 + 0.60*0.3 = 0.60
        result = self.calculator.compute(
            decision_confidence=0.60,
            quality_score=0.60,
            execution_status="success",
        )
        self.assertEqual(result.action, ACTION_REVIEW)
        self.assertTrue(DEFAULT_REVIEW_THRESHOLD <= result.confidence < DEFAULT_DELIVER_THRESHOLD)

    def test_31_review_above_threshold(self):
        """31. confidence entre 0.60 e 0.80 → review."""
        result = self.calculator.compute(
            decision_confidence=0.7,
            quality_score=0.7,
            execution_status="success",
        )
        # 0.7*0.7 + 0.7*0.3 = 0.7
        self.assertEqual(result.action, ACTION_REVIEW)

    def test_32_reselect_below_review_threshold(self):
        """32. confidence < 0.60 → reselect."""
        result = self.calculator.compute(
            decision_confidence=0.3,
            quality_score=0.5,
            execution_status="success",
        )
        # 0.5*0.7 + 0.3*0.3 = 0.35 + 0.09 = 0.44
        self.assertEqual(result.action, ACTION_RESELECT)
        self.assertTrue(result.confidence < DEFAULT_REVIEW_THRESHOLD)

    def test_33_reason_populated_deliver(self):
        """33. reason string não-vazia para deliver."""
        result = self.calculator.compute(
            decision_confidence=1.0,
            quality_score=1.0,
            execution_status="success",
        )
        self.assertIsInstance(result.reason, str)
        self.assertTrue(result.reason.strip())
        self.assertIn("deliver", result.reason.lower())

    def test_34_reason_populated_review(self):
        """34. reason string não-vazia para review."""
        result = self.calculator.compute(
            decision_confidence=0.7,
            quality_score=0.7,
            execution_status="success",
        )
        self.assertIsInstance(result.reason, str)
        self.assertTrue(result.reason.strip())
        self.assertIn("review", result.reason.lower())

    def test_35_reason_populated_reselect(self):
        """35. reason string não-vazia para reselect."""
        result = self.calculator.compute(
            decision_confidence=0.1,
            quality_score=0.2,
            execution_status="success",
        )
        self.assertIsInstance(result.reason, str)
        self.assertTrue(result.reason.strip())
        self.assertIn("reselect", result.reason.lower())

    def test_36_metadata_populated(self):
        """36. metadata contém inputs, pesos, thresholds."""
        result = self.calculator.compute(
            decision_confidence=0.8,
            quality_score=0.9,
            execution_status="success",
        )
        meta = result.metadata
        self.assertEqual(meta["decision_confidence"], 0.8)
        self.assertEqual(meta["quality_score"], 0.9)
        self.assertEqual(meta["execution_status"], "success")
        self.assertIn("weights", meta)
        self.assertIn("thresholds", meta)
        self.assertIn("computed_confidence", meta)

    def test_37_deterministic(self):
        """37. Mesma entrada → mesma saída (determinístico)."""
        for _ in range(10):
            r1 = self.calculator.compute(0.7, 0.8, "success")
            r2 = self.calculator.compute(0.7, 0.8, "success")
            self.assertEqual(r1.confidence, r2.confidence)
            self.assertEqual(r1.action, r2.action)
            self.assertEqual(r1.reason, r2.reason)

    def test_38_inputs_not_mutated(self):
        """38. Inputs não são mutados (não aplicável mas sanity check)."""
        dc = 0.8
        qs = 0.9
        es = "success"
        self.calculator.compute(dc, qs, es)
        # Primitivos são imutáveis em Python, mas verificamos
        self.assertEqual(dc, 0.8)
        self.assertEqual(qs, 0.9)
        self.assertEqual(es, "success")


class TestFinalConfidenceCalculatorCustomConfig(unittest.TestCase):
    """Testes com configuração customizada."""

    def test_39_custom_weights(self):
        """39. Pesos customizados afetam o score."""
        config = FinalConfidenceConfig(quality_weight=0.5, decision_weight=0.5)
        calc = FinalConfidenceCalculator(config=config)
        # 0.8*0.5 + 0.4*0.5 = 0.6
        result = calc.compute(0.4, 0.8, "success")
        self.assertAlmostEqual(result.confidence, 0.6, places=5)

    def test_40_custom_thresholds(self):
        """40. Thresholds customizados mudam ação."""
        config = FinalConfidenceConfig(
            quality_weight=0.7,
            decision_weight=0.3,
            deliver_threshold=0.9,
            review_threshold=0.5,
        )
        calc = FinalConfidenceCalculator(config=config)
        # confidence = 0.7*0.8 + 0.3*0.8 = 0.8
        # deliver=0.9, review=0.5 → 0.8 >= 0.5 and < 0.9 → review
        result = calc.compute(0.8, 0.8, "success")
        self.assertEqual(result.action, ACTION_REVIEW)

    def test_41_convenience_function(self):
        """41. Função de conveniência compute_final_confidence funciona."""
        result = compute_final_confidence(
            decision_confidence=0.9,
            quality_score=0.9,
            execution_status="success",
        )
        self.assertIsInstance(result, FinalConfidenceResult)
        self.assertEqual(result.action, ACTION_DELIVER)

    def test_42_convenience_function_custom_params(self):
        """42. Função de conveniência aceita parâmetros customizados."""
        result = compute_final_confidence(
            decision_confidence=0.5,
            quality_score=0.5,
            execution_status="success",
            quality_weight=0.6,
            decision_weight=0.4,
            deliver_threshold=0.7,
            review_threshold=0.4,
        )
        # 0.5*0.6 + 0.5*0.4 = 0.5
        # review threshold 0.4, deliver 0.7 → review
        self.assertEqual(result.action, ACTION_REVIEW)


class TestConceptSeparation(unittest.TestCase):
    """Testes garantindo separação de conceitos obrigatória."""

    def test_43_decision_confidence_vs_quality_score_vs_final(self):
        """43. DecisionConfidence ≠ QualityScore ≠ FinalConfidence."""
        calc = FinalConfidenceCalculator()
        result = calc.compute(
            decision_confidence=0.95,  # alta decisão
            quality_score=0.20,        # baixa qualidade
            execution_status="success",
        )
        # Final confidence = 0.20*0.7 + 0.95*0.3 = 0.14 + 0.285 = 0.425
        self.assertNotEqual(result.confidence, 0.95)
        self.assertNotEqual(result.confidence, 0.20)
        self.assertAlmostEqual(result.confidence, 0.425, places=3)
        # Final está entre os dois (weighted average)
        self.assertGreater(result.confidence, 0.20)
        self.assertLess(result.confidence, 0.95)

    def test_44_execution_status_not_confidence(self):
        """44. ExecutionStatus não é confundido com confidence."""
        calc = FinalConfidenceCalculator()
        # Sucesso técnico mas baixa qualidade
        result = calc.compute(
            decision_confidence=0.5,
            quality_score=0.1,
            execution_status="success",
        )
        self.assertEqual(result.metadata["execution_status"], "success")
        self.assertLess(result.confidence, 0.5)

    def test_45_no_llm_no_network(self):
        """45. Nenhuma dependência LLM/rede no módulo."""
        import olympus.judge.final_confidence as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        for token in ("anthropic", "openai", "openrouter", "claude", "gpt",
                      "urllib", "requests", "socket", "http://", "https://"):
            self.assertNotIn(token, source.lower())


class TestEdgeCases(unittest.TestCase):
    """Casos de borda."""

    def test_46_zero_quality_max_decision(self):
        """46. quality=0, decision=1 → confidence = 0.3 (decision_weight)."""
        result = compute_final_confidence(1.0, 0.0, "success")
        self.assertAlmostEqual(result.confidence, DEFAULT_DECISION_WEIGHT, places=5)

    def test_47_max_quality_zero_decision(self):
        """47. quality=1, decision=0 → confidence = 0.7 (quality_weight)."""
        result = compute_final_confidence(0.0, 1.0, "success")
        self.assertAlmostEqual(result.confidence, DEFAULT_QUALITY_WEIGHT, places=5)

    def test_48_both_zero(self):
        """48. Ambos zero → confidence=0, action=reselect."""
        result = compute_final_confidence(0.0, 0.0, "success")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.action, ACTION_RESELECT)

    def test_49_both_one(self):
        """49. Ambos um → confidence=1, action=deliver."""
        result = compute_final_confidence(1.0, 1.0, "success")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.action, ACTION_DELIVER)

    def test_50_confidence_clamped(self):
        """50. Confidence clampado em [0,1] (safety net)."""
        # Pesos customizados que poderiam extrapolar (embora validação evite)
        config = FinalConfidenceConfig(quality_weight=0.7, decision_weight=0.3)
        calc = FinalConfidenceCalculator(config=config)
        # Mesmo com inputs válidos, clamp garante
        result = calc.compute(1.0, 1.0, "success")
        self.assertLessEqual(result.confidence, 1.0)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_51_case_insensitive_execution_status(self):
        """51. Execution status case-sensitive (exato)."""
        calc = FinalConfidenceCalculator()
        # "Success" ≠ "success"
        result = calc.compute(0.8, 0.8, "Success")
        self.assertEqual(result.action, ACTION_RESELECT)
        self.assertEqual(result.confidence, 0.0)

    def test_52_metadata_includes_computed_confidence(self):
        """52. metadata.computed_confidence == result.confidence."""
        calc = FinalConfidenceCalculator()
        result = calc.compute(0.7, 0.8, "success")
        self.assertEqual(result.metadata["computed_confidence"], result.confidence)


if __name__ == "__main__":
    unittest.main()