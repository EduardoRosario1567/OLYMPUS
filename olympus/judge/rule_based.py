"""
RuleBasedJudge — PATCH 005B

Primeiro evaluator concreto do Judge Engine.

100% determinístico. Zero chamadas LLM. Zero rede. Zero custo externo.

Propósito:
    Identificar problemas BÁSICOS de qualidade que não exigem inteligência
    de outro modelo: output vazio, conteúdo insuficiente, falta de estrutura
    esperada. NÃO tenta provar correção semântica, factual ou de segurança.

Regras:
    - Nova dependência de provider/modelo: NENHUMA.
    - Novo mecanismo externo: NENHUM.
    - Imutabilidade: JudgeContext nunca é mutado.
    - Autoridade de decisão: DecisionEngine/Pipeline não são afetados.
"""

import re
from typing import Optional

from olympus.judge.interfaces import (
    EvaluationPolicy,
    JudgeAdapter,
    JudgeContext,
    JudgeResult,
)

# Valor canônico de ExecutionStatus.SUCCESS.value (não importamos models aqui
# para manter o omnisciente desacoplado e dentro do escopo autorizado).
_SUCCESS_STATUS = "success"

# Task type que recebe checagem estrutural de código.
_CODIGO_TASK_TYPE = "codigo"

# Limite documentado (caracteres) para "conteúdo mínimo" do output.
_MIN_CONTENT_CHARS = 15

# Pesos padrão estáveis (iguais) quando a policy não define pesos próprios.
_DEFAULT_WEIGHT = 1.0


class RuleBasedJudge:
    """
    Judge determinístico baseado em regras.

    Implementa JudgeAdapter via duck-typing (satisfaz o Protocol).

    Uso:
        judge = RuleBasedJudge(policy=my_policy)
        result = judge.evaluate(context)

    evaluator: "rule_based"
    """

    evaluator = "rule_based"

    def __init__(self, policy: EvaluationPolicy) -> None:
        """
        Args:
            policy: EvaluationPolicy que define pass_threshold e (opcionalmente)
                critérios/pesos para a média ponderada.
        """
        self._policy = policy

    # ------------------------------------------------------------------
    # JudgeAdapter
    # ------------------------------------------------------------------

    def evaluate(self, context: JudgeContext) -> JudgeResult:
        """Avalia o contexto e retorna JudgeResult determinístico."""
        # Pré-condição: falha técnica de execução → short-circuit.
        # Não julgamos qualidade de conteúdo de execução que falhou tecnicamente.
        if context.execution_status != _SUCCESS_STATUS:
            return self._technical_failure_result(context)

        # Sinais determinísticos.
        signals = self._compute_signals(context)

        # Pesos (da policy, se definidos; senão, default estável).
        weights = self._resolve_weights(signals)
        quality_score = self._weighted_score(signals, weights)

        threshold = self._policy.pass_threshold
        passed = quality_score >= threshold

        reason = self._build_reason(signals, passed, threshold)

        criteria = {name: round(score, 5) for name, score in signals.items()}
        metadata = {
            "signal_weights": weights,
            "task_type": context.task_type,
            "policy_threshold": threshold,
            "minimum_content_chars": _MIN_CONTENT_CHARS,
        }

        return JudgeResult(
            quality_score=quality_score,
            passed=passed,
            evaluator=self.evaluator,
            reason=reason,
            criteria=criteria,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Sinais
    # ------------------------------------------------------------------

    def _compute_signals(self, context: JudgeContext) -> dict:
        """Calcula os sinais determinísticos como dict nome → score [0.0, 1.0]."""
        raw_output = context.output if context.output else ""
        stripped = raw_output.strip()

        signals = {}
        signals["non_empty_output"] = 1.0 if stripped else 0.0
        signals["minimum_content"] = 1.0 if len(stripped) >= _MIN_CONTENT_CHARS else 0.0

        task_type = (context.task_type or "").lower()
        if task_type == _CODIGO_TASK_TYPE:
            signals["expected_structure"] = 1.0 if self._detect_code_structure(stripped) else 0.0
        else:
            # Caminho genérico: sem assunção semântica sobre estrutura.
            # structural_completeness fica neutro (1.0) — não há como saber
            # a estrutura correta sem conhecimento de domínio.
            signals["structural_completeness"] = 1.0

        return signals

    def _detect_code_structure(self, text: str) -> bool:
        """
        Detecção BÁSICA e defensável de presença de código.

        Sinais estruturais simples (sem executar, sem julgar correção):
          - bloco de código (fence ``` / ```python)
          - definição de função (def) ou classe (class)
          - declaração de import
          - statement de return
        """
        if not text:
            return False
        if "```" in text:
            return True
        if re.search(r"\bdef\s+[A-Za-z_]\w*\s*\(", text):  # def nome(:
            return True
        if re.search(r"\bclass\s+[A-Za-z_]\w*", text):     # class Nome:
            return True
        if re.search(r"^\s*(import|from)\s+\w+", text, flags=re.MULTILINE):
            return True
        if re.search(r"\breturn\b", text):
            return True
        return False

    # ------------------------------------------------------------------
    # Pesos e score
    # ------------------------------------------------------------------

    def _resolve_weights(self, signals: dict) -> dict:
        """
        Resolve pesos por sinal.

        Ordem de precedência:
          1. policy.metadata["weights"] — dict sinal → peso numérico (>= 0)
          2. policy.criteria com valores numéricos correspondentes aos sinais
          3. default estável (pesos iguais)
        """
        metadata = getattr(self._policy, "metadata", None) or {}
        weights = metadata.get("weights")
        if isinstance(weights, dict) and weights:
            resolved = {name: float(w) for name, w in weights.items()
                        if name in signals and self._valid_weight(w)}
            if resolved:
                return resolved

        criteria = getattr(self._policy, "criteria", None) or {}
        if criteria:
            resolved = {name: float(w) for name, w in criteria.items()
                        if name in signals and self._valid_weight(w)}
            if resolved:
                return resolved

        return {name: _DEFAULT_WEIGHT for name in signals}

    @staticmethod
    def _valid_weight(value) -> bool:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        return v >= 0

    def _weighted_score(self, signals: dict, weights: dict) -> float:
        """Média ponderada determinística; clamp final [0.0, 1.0]."""
        total_weight = sum(weights[name] for name in signals if name in weights)
        if total_weight <= 0:
            return 0.0
        weighted = sum(signals[name] * weights.get(name, 0.0) for name in signals)
        score = weighted / total_weight
        # Clamp por segurança (média de valores em [0,1] já satisfaz, mas defesa extra).
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Razão
    # ------------------------------------------------------------------

    def _build_reason(self, signals: dict, passed: bool, threshold: float) -> str:
        if not signals.get("non_empty_output"):
            return (
                "Output está vazio ou é apenas espaços em branco; "
                "provável falha de qualidade. Não é possível avaliar conteúdo."
            )
        if not signals.get("minimum_content"):
            return (
                "Output possui conteúdo insuficiente (abaixo do mínimo de "
                f"{_MIN_CONTENT_CHARS} caracteres) para uma avaliação mínima."
            )
        if "expected_structure" in signals and not signals["expected_structure"]:
            return (
                "Output não contém estrutura de código esperada para uma tarefa "
                "de código (sem definição de função/classe, bloco ou return)."
            )
        if passed:
            return (
                "Output passou nas checagens determinísticas básicas: não-vazio, "
                "conteúdo suficiente e estrutura esperada presente."
            )
        return (
            "Output passou nas checagens básicas, mas o score calculado está abaixo "
            f"do threshold da policy ({threshold:.2f})."
        )

    # ------------------------------------------------------------------
    # Falha técnica
    # ------------------------------------------------------------------

    def _technical_failure_result(self, context: JudgeContext) -> JudgeResult:
        """Short-circuit determinístico para execução que falhou tecnicamente."""
        return JudgeResult(
            quality_score=0.0,
            passed=False,
            evaluator=self.evaluator,
            reason=(
                f"Technical execution did not succeed (status='{context.execution_status}'); "
                "quality of content is not evaluated."
            ),
            criteria={"technical_failure": 0.0},
            metadata={
                "execution_status": context.execution_status,
                "task_type": context.task_type,
            },
        )
