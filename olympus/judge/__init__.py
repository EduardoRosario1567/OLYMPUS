"""
Judge Engine — PATCH 005A + 005B + 005C + 005F

Contratos, interfaces, e implementações para avaliação de qualidade de resultados.
Completamente desacoplado de providers, modelos, RoutingAdapter e OmniRoute.
"""

from olympus.judge.interfaces import (
    EvaluationPolicy,
    JudgeAdapter,
    JudgeContext,
    JudgeResult,
    SimpleEvaluationPolicy,
)
from olympus.judge.rule_based import RuleBasedJudge
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

__all__ = [
    "EvaluationPolicy",
    "JudgeAdapter",
    "JudgeContext",
    "JudgeResult",
    "SimpleEvaluationPolicy",
    "RuleBasedJudge",
    "TASK_TYPE_CODIGO",
    "TASK_TYPE_TEXTO",
    "TASK_TYPE_ARQUITETURA",
    "CODIGO_CRITERIA",
    "TEXTO_CRITERIA",
    "ARQUITETURA_CRITERIA",
    "CODIGO_DEFAULT_THRESHOLD",
    "TEXTO_DEFAULT_THRESHOLD",
    "ARQUITETURA_DEFAULT_THRESHOLD",
    "DomainEvaluationPolicy",
    "default_codigo_policy",
    "default_texto_policy",
    "default_arquitetura_policy",
    "to_simple_policy",
    "FinalConfidenceConfig",
    "FinalConfidenceResult",
    "FinalConfidenceCalculator",
    "compute_final_confidence",
    "ACTION_DELIVER",
    "ACTION_REVIEW",
    "ACTION_RESELECT",
    "DEFAULT_QUALITY_WEIGHT",
    "DEFAULT_DECISION_WEIGHT",
    "DEFAULT_DELIVER_THRESHOLD",
    "DEFAULT_REVIEW_THRESHOLD",
]