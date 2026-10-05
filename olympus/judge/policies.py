"""
Domain Evaluation Policies — PATCH 005C

Políticas de avaliação por domínio de tarefa.

Uma policy declara:
- task_type: tipo de tarefa a que se aplica
- pass_threshold: score mínimo para passar
- criteria: nomes dos critérios esperados (extensíveis)
- metadata: pesos e metadados opcionais

Uma policy NÃO calcula quality_score — isso é responsabilidade do evaluator.
"""

from dataclasses import dataclass
from typing import Optional, Dict

from olympus.judge.interfaces import SimpleEvaluationPolicy


# Constantes de task_type para consistência
TASK_TYPE_CODIGO = "codigo"
TASK_TYPE_TEXTO = "texto"
TASK_TYPE_ARQUITETURA = "arquitetura"


# Critérios canônicos por domínio (nomes estáveis)
CODIGO_CRITERIA = {
    "non_empty_output": 1.0,
    "minimum_content": 1.0,
    "expected_structure": 1.0,
}

TEXTO_CRITERIA = {
    "non_empty_output": 1.0,
    "minimum_content": 1.0,
}

ARQUITETURA_CRITERIA = {
    "non_empty_output": 1.0,
    "minimum_content": 1.0,
    "structural_completeness": 1.0,
}


# Thresholds padrão por domínio
CODIGO_DEFAULT_THRESHOLD = 0.6
TEXTO_DEFAULT_THRESHOLD = 0.5
ARQUITETURA_DEFAULT_THRESHOLD = 0.6


@dataclass(frozen=True)
class DomainEvaluationPolicy:
    """
    Policy de domínio imutável e tipada.

    Extende SimpleEvaluationPolicy com semântica de domínio explícita.
    Não adiciona comportamento — apenas garante consistência de nomes.
    """
    task_type: str
    minimum_quality_score: float
    criteria: Dict[str, float]
    metadata: Optional[Dict] = None

    @property
    def pass_threshold(self) -> float:
        return self.minimum_quality_score

    def __post_init__(self) -> None:
        if not (0.0 <= self.minimum_quality_score <= 1.0):
            raise ValueError(
                f"minimum_quality_score must be in [0.0, 1.0], got {self.minimum_quality_score}"
            )
        if self.criteria is None:
            object.__setattr__(self, "criteria", {})
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


def default_codigo_policy(
    threshold: float = CODIGO_DEFAULT_THRESHOLD,
    weights: Optional[Dict[str, float]] = None,
    metadata: Optional[Dict] = None,
) -> DomainEvaluationPolicy:
    """
    Factory para policy CODIGO padrão.

    Args:
        threshold: Score mínimo para passar (default 0.6)
        weights: Pesos opcionais por critério (ex: {"expected_structure": 2.0})
        metadata: Metadados adicionais (mesclado com weights)

    Returns:
        DomainEvaluationPolicy imutável para tarefas de código.
    """
    merged_metadata = dict(metadata) if metadata else {}
    if weights:
        merged_metadata["weights"] = weights
    return DomainEvaluationPolicy(
        task_type=TASK_TYPE_CODIGO,
        minimum_quality_score=threshold,
        criteria=dict(CODIGO_CRITERIA),
        metadata=merged_metadata,
    )


def default_texto_policy(
    threshold: float = TEXTO_DEFAULT_THRESHOLD,
    weights: Optional[Dict[str, float]] = None,
    metadata: Optional[Dict] = None,
) -> DomainEvaluationPolicy:
    """
    Factory para policy TEXTO padrão.

    Args:
        threshold: Score mínimo para passar (default 0.5)
        weights: Pesos opcionais por critério
        metadata: Metadados adicionais (mesclado com weights)

    Returns:
        DomainEvaluationPolicy imutável para tarefas de texto livre.
    """
    merged_metadata = dict(metadata) if metadata else {}
    if weights:
        merged_metadata["weights"] = weights
    return DomainEvaluationPolicy(
        task_type=TASK_TYPE_TEXTO,
        minimum_quality_score=threshold,
        criteria=dict(TEXTO_CRITERIA),
        metadata=merged_metadata,
    )


def default_arquitetura_policy(
    threshold: float = ARQUITETURA_DEFAULT_THRESHOLD,
    weights: Optional[Dict[str, float]] = None,
    metadata: Optional[Dict] = None,
) -> DomainEvaluationPolicy:
    """
    Factory para policy ARQUITETURA padrão.

    Args:
        threshold: Score mínimo para passar (default 0.6)
        weights: Pesos opcionais por critério
        metadata: Metadados adicionais (mesclado com weights)

    Returns:
        DomainEvaluationPolicy imutável para tarefas de arquitetura/design.
    """
    merged_metadata = dict(metadata) if metadata else {}
    if weights:
        merged_metadata["weights"] = weights
    return DomainEvaluationPolicy(
        task_type=TASK_TYPE_ARQUITETURA,
        minimum_quality_score=threshold,
        criteria=dict(ARQUITETURA_CRITERIA),
        metadata=merged_metadata,
    )


# Helpers para compatibilidade com SimpleEvaluationPolicy existente
def to_simple_policy(domain_policy: DomainEvaluationPolicy) -> SimpleEvaluationPolicy:
    """Converte DomainEvaluationPolicy para SimpleEvaluationPolicy."""
    return SimpleEvaluationPolicy(
        task_type=domain_policy.task_type,
        minimum_quality_score=domain_policy.minimum_quality_score,
        criteria=domain_policy.criteria,
        metadata=domain_policy.metadata,
    )


__all__ = [
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
]