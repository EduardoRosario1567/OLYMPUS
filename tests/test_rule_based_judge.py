"""Testes do RuleBasedJudge — PATCH 005B.

Valida o primeiro evaluator concreto do Judge Engine:
100% determinístico, zero LLM, zero rede, zero OmniRoute.
"""

import copy
import os
import unittest

from olympus.judge.interfaces import (
    JudgeAdapter,
    JudgeResult,
    SimpleEvaluationPolicy,
)
from olympus.judge.rule_based import RuleBasedJudge

DEFAULT_POLICY = SimpleEvaluationPolicy(
    task_type="codigo",
    minimum_quality_score=0.6,
)

GOOD_CODE = (
    "def primos(n):\n"
    "    return [i for i in range(2, n+1) "
    "if all(i % j for j in range(2, int(i**0.5)+1))]\n"
)

LONG_PROSE = (
    "This is a sufficiently long response with enough words "
    "to be considered meaningful content for a basic evaluation."
)


def make_context(
    task_type: str = "codigo",
    output: str = GOOD_CODE,
    status: str = "success",
    task_desc: str = "Escreva uma função Python",
) -> "JudgeContext":
    from olympus.judge.interfaces import JudgeContext
    return JudgeContext(
        task_id="task-1",
        task_type=task_type,
        task_description=task_desc,
        decision_id="dec-1",
        decision_confidence=0.85,
        execution_result_id="exec-1",
        requested_model="openrouter/cohere/north-mini-code:free",
        actual_model="cohere/north-mini-code:free",
        provider="cohere",
        output=output,
        execution_status=status,
        metadata={"correlation_id": "corr-123"},
    )


class TestRuleBasedJudgeContract(unittest.TestCase):
    """Testes de contrato e semântica básica."""

    def setUp(self):
        self.judge = RuleBasedJudge(policy=DEFAULT_POLICY)

    def test_1_implements_judge_adapter(self):
        """1. RuleBasedJudge satisfaz JudgeAdapter (protocol)."""
        self.assertIsInstance(self.judge, JudgeAdapter)

    def test_2_success_good_output(self):
        """2. Sucesso técnico + bom output → passa."""
        ctx = make_context()
        result = self.judge.evaluate(ctx)
        self.assertIsInstance(result, JudgeResult)
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.quality_score, 0.6)
        self.assertEqual(result.quality_score, 1.0)

    def test_3_empty_output(self):
        """3. Output vazio → falha."""
        ctx = make_context(output="")
        result = self.judge.evaluate(ctx)
        self.assertFalse(result.passed)
        self.assertEqual(result.quality_score, 0.0)
        self.assertEqual(result.criteria["non_empty_output"], 0.0)

    def test_4_whitespace_output(self):
        """4. Output só com espaços em branco → falha."""
        ctx = make_context(output="   \n\t  ")
        result = self.judge.evaluate(ctx)
        self.assertFalse(result.passed)
        self.assertEqual(result.quality_score, 0.0)

    def test_5_execution_failure_short_circuit(self):
        """5. Falha técnica de execução → score 0, sem julgar conteúdo."""
        ctx = make_context(status="timeout")
        result = self.judge.evaluate(ctx)
        self.assertEqual(result.quality_score, 0.0)
        self.assertFalse(result.passed)
        self.assertIn("did not succeed", result.reason)
        self.assertEqual(result.criteria, {"technical_failure": 0.0})

    def test_6_short_output(self):
        """6. Output curto demais → minimum_content = 0."""
        ctx = make_context(output="ok")
        result = self.judge.evaluate(ctx)
        self.assertEqual(result.criteria["non_empty_output"], 1.0)
        self.assertEqual(result.criteria["minimum_content"], 0.0)
        self.assertFalse(result.passed)

    def test_7_sufficient_output(self):
        """7. Output suficiente → minimum_content = 1."""
        ctx = make_context(output="return 42 " * 8)  # texto longo com código
        result = self.judge.evaluate(ctx)
        self.assertEqual(result.criteria["minimum_content"], 1.0)


class TestRuleBasedJudgeCodigo(unittest.TestCase):
    """Testes do caminho CODIGO."""

    def setUp(self):
        self.judge = RuleBasedJudge(policy=DEFAULT_POLICY)

    def test_8_codigo_with_code_structure(self):
        """8. CODIGO com função/return → expected_structure = 1."""
        ctx = make_context(task_type="codigo", output=GOOD_CODE)
        result = self.judge.evaluate(ctx)
        self.assertEqual(result.criteria["expected_structure"], 1.0)
        self.assertTrue(result.passed)

    def test_9_codigo_without_code_structure(self):
        """9. CODIGO sem estrutura de código → expected_structure = 0."""
        ctx = make_context(task_type="codigo", output=LONG_PROSE)
        result = self.judge.evaluate(ctx)
        self.assertEqual(result.criteria["expected_structure"], 0.0)
        # score reduzido abaixo do caso com estrutura
        self.assertLess(result.quality_score, 1.0)

    def test_10_non_codigo_generic_path(self):
        """10. Não-CODIGO usa caminho genérico, sem assunção de estrutura."""
        ctx = make_context(task_type="texto", output=LONG_PROSE)
        result = self.judge.evaluate(ctx)
        self.assertEqual(result.criteria["structural_completeness"], 1.0)
        self.assertNotIn("expected_structure", result.criteria)
        self.assertTrue(result.passed)


class TestRuleBasedJudgeScoring(unittest.TestCase):
    """Testes de scoring determinístico."""

    def setUp(self):
        self.judge = RuleBasedJudge(policy=DEFAULT_POLICY)

    def test_11_score_range(self):
        """11. quality_score sempre em [0.0, 1.0]."""
        for output in ["", "  ", "ok", LONG_PROSE, GOOD_CODE]:
            ctx = make_context(output=output)
            result = self.judge.evaluate(ctx)
            self.assertGreaterEqual(result.quality_score, 0.0)
            self.assertLessEqual(result.quality_score, 1.0)

    def test_12_pass_threshold(self):
        """12. score >= threshold → passed."""
        ctx = make_context(output=GOOD_CODE)
        result = self.judge.evaluate(ctx)
        self.assertTrue(result.passed)

    def test_13_fail_threshold(self):
        """13. score < threshold → failed."""
        ctx = make_context(output="ok")
        result = self.judge.evaluate(ctx)
        self.assertFalse(result.passed)

    def test_14_criteria_populated(self):
        """14. criteria contém scores medidos reais."""
        ctx = make_context(output=GOOD_CODE)
        result = self.judge.evaluate(ctx)
        for name in ("non_empty_output", "minimum_content", "expected_structure"):
            self.assertIn(name, result.criteria)

    def test_15_evaluator_rule_based(self):
        """15. evaluator == 'rule_based'."""
        result = self.judge.evaluate(make_context())
        self.assertEqual(result.evaluator, "rule_based")

    def test_16_reason_populated(self):
        """16. reason é string não-vazia e legível."""
        result = self.judge.evaluate(make_context())
        self.assertIsInstance(result.reason, str)
        self.assertTrue(result.reason.strip())

    def test_17_metadata_populated(self):
        """17. metadata populado onde apropriado."""
        result = self.judge.evaluate(make_context())
        self.assertIn("signal_weights", result.metadata)
        self.assertIn("task_type", result.metadata)
        self.assertIn("minimum_content_chars", result.metadata)

    def test_18_deterministic(self):
        """18. Mesma entrada → mesma saída (determinístico)."""
        ctx = make_context(output=GOOD_CODE)
        r1 = self.judge.evaluate(ctx)
        r2 = self.judge.evaluate(ctx)
        self.assertEqual(r1.quality_score, r2.quality_score)
        self.assertEqual(r1.criteria, r2.criteria)
        self.assertEqual(r1.passed, r2.passed)

    def test_19_context_not_mutated(self):
        """19. JudgeContext não é mutado pela avaliação."""
        ctx = make_context(output=GOOD_CODE)
        snapshot = copy.deepcopy(ctx)
        self.judge.evaluate(ctx)
        self.assertEqual(ctx.task_id, snapshot.task_id)
        self.assertEqual(ctx.task_type, snapshot.task_type)
        self.assertEqual(ctx.task_description, snapshot.task_description)
        self.assertEqual(ctx.output, snapshot.output)
        self.assertEqual(ctx.execution_status, snapshot.execution_status)
        self.assertEqual(ctx.metadata, snapshot.metadata)


class TestRuleBasedJudgeIsolation(unittest.TestCase):
    """Testes de isolamento (zero dependências externas)."""

    def test_20_no_network_dependency(self):
        """20. Nenhuma dependência de rede no módulo."""
        import olympus.judge.rule_based as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        for token in ("urllib", "requests", "socket", "urlopen", "http://", "https://"):
            self.assertNotIn(token, source)

    def test_21_no_omniroute_dependency(self):
        """21. Nenhuma dependência de OmniRoute."""
        import olympus.judge.rule_based as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("OmniRoute", source)
        self.assertNotIn("omniroute", source.lower())

    def test_22_no_llm_dependency(self):
        """22. Nenhuma dependência de LLM."""
        import olympus.judge.rule_based as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        for token in ("anthropic", "openai", "openrouter", "claude", "gpt"):
            self.assertNotIn(token, source.lower())
        self.assertNotIn("subprocess", source)

    def test_no_execution_of_generated_code(self):
        """Não há eval/exec de código gerado."""
        import olympus.judge.rule_based as mod
        source = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("exec(", source)
        self.assertNotIn("eval(", source)


class TestRuleBasedJudgePolicy(unittest.TestCase):
    """Testes de policy customizada."""

    def test_23_custom_policy_threshold(self):
        """23. Threshold customizado define passed."""
        strict_policy = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.9,
        )
        judge = RuleBasedJudge(policy=strict_policy)

        # CODIGO sem estrutura → score ~0.667 < 0.9 → falha
        ctx_no_struct = make_context(task_type="codigo", output=LONG_PROSE)
        result = judge.evaluate(ctx_no_struct)
        self.assertFalse(result.passed)

        # CODIGO com estrutura → score 1.0 >= 0.9 → passa
        ctx_good = make_context(task_type="codigo", output=GOOD_CODE)
        result2 = judge.evaluate(ctx_good)
        self.assertTrue(result2.passed)

    def test_24_custom_weights(self):
        """24. Pesos customizados via policy afetam a média ponderada."""
        weighted_policy = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            metadata={"weights": {"non_empty_output": 1.0, "minimum_content": 1.0, "expected_structure": 2.0}},
        )
        judge = RuleBasedJudge(policy=weighted_policy)

        # CODIGO sem estrutura: (1*1 + 1*1 + 0*2)/4 = 0.5
        ctx = make_context(task_type="codigo", output=LONG_PROSE)
        result = judge.evaluate(ctx)
        self.assertAlmostEqual(result.quality_score, 0.5, places=4)
        self.assertFalse(result.passed)
        self.assertEqual(result.metadata["signal_weights"]["expected_structure"], 2.0)

    def test_criteria_not_used_as_weights_when_non_signal(self):
        """Critérios que não correspondem a sinais não alteram o score."""
        policy_with_criteria = SimpleEvaluationPolicy(
            task_type="codigo",
            minimum_quality_score=0.6,
            criteria={"correctness": 0.9, "completeness": 0.9},
        )
        judge = RuleBasedJudge(policy=policy_with_criteria)
        ctx = make_context(task_type="codigo", output=GOOD_CODE)
        result = judge.evaluate(ctx)
        # Fallback para pesos iguais → score 1.0
        self.assertAlmostEqual(result.quality_score, 1.0, places=4)


if __name__ == "__main__":
    unittest.main()