"""
Entidades centrais do Olympus (versão in-memory, Fase 1 - Cérebro).
Sem persistência: isso vem na etapa 2 (modelagem de dados / schema).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class TaskType(str, Enum):
    TEXTO = "texto"
    CODIGO = "codigo"
    ARQUITETURA = "arquitetura"
    REVISAO = "revisao"
    IMAGEM = "imagem"
    DOCUMENTACAO = "documentacao"
    TESTES = "testes"
    INTEGRACAO = "integracao"
    RESPOSTA_CURTA = "resposta_curta"
    RESPOSTA_LONGA = "resposta_longa"


class Prioridade(str, Enum):
    CUSTO = "custo"
    QUALIDADE = "qualidade"
    VELOCIDADE = "velocidade"


@dataclass
class Modelo:
    id: str
    nome: str
    provedor: str
    capacidades: list[TaskType]
    custo_estimado: float          # custo relativo por execução (quanto menor, mais barato)
    latencia_estimada: float       # segundos, estimados
    confiabilidade: float          # 0.0 a 1.0
    prioridade: int = 0            # desempate manual (maior = preferido)
    ativo: bool = True
    # Capability matrix used by the multi-brain router. Defaults preserve
    # compatibility with every legacy Modelo constructor.
    context_window: int = 0
    coding_strength: float = 0.5
    reasoning_strength: float = 0.5
    agentic_strength: float = 0.5
    tool_use_strength: float = 0.5
    recovery_strength: float = 0.5
    structured_output_strength: float = 0.5
    observed_attempts: int = 0
    observed_successes: int = 0
    observed_timeouts: int = 0
    observed_latency_ms: float = 0.0

    def suporta(self, tipo: TaskType) -> bool:
        return self.ativo and tipo in self.capacidades


@dataclass
class Tarefa:
    id: str
    projeto_id: str
    descricao: str
    tipo: Optional[TaskType] = None
    critica: bool = False
    urgente: bool = False
    prioridade: Prioridade = Prioridade.QUALIDADE
    modelo_sugerido: Optional[str] = None
    status: str = "pendente"
    limite_custo: Optional[float] = None  # custo máximo aceitável para esta tarefa


@dataclass
class DecisaoRegistro:
    """Log de auditoria de uma decisão do motor (princípio: toda decisão é auditável)."""
    tarefa_id: str
    modelo_escolhido: Optional[str]
    candidatos_avaliados: list[str]
    motivo: str
    fallback_usado: bool
    confianca: float
    downgrade_usado: bool = False
    decisao_status: str = "approved"  # approved | fallback | downgraded (mapeia para decision_status no DB)
    custo_estimado: float = 0.0        # custo do modelo efetivamente escolhido
    latencia_estimada_ms: int = 0      # latência do modelo efetivamente escolhido
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ExecutionStatus(str, Enum):
    """Status técnico do resultado de execução (PATCH 004C).

    Distingue falha técnica de execução de qualidade da resposta.
    "success" significa apenas: execução técnica recebeu e parseou resposta válida.
    NÃO significa resposta de boa qualidade.
    """
    SUCCESS = "success"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    BILLING_ERROR = "billing_error"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_ERROR = "authentication_error"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN_ERROR = "unknown_error"


class ExecutionResult:
    """Resultado real da execução de um modelo — separado da decisão (PATCH 004B).

    DECISION = "O que Olympus decidiu?"
    EXECUTION RESULT = "O que realmente aconteceu?"
    """
    id: str
    execution_id: str
    decision_record_id: str

    requested_model: str
    actual_model: str
    provider: str

    output: str
    latency_ms: int
    cost: float

    success: bool
    error: Optional[str] = None
    status: str = ExecutionStatus.SUCCESS.value  # ExecutionStatus enum values

    correlation_id: Optional[str] = None
    usage: Optional[dict] = None
    metadata: Optional[dict] = None

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class QualityEvaluation:
    """Avaliação de qualidade de um resultado de execução — PATCH 005D.

    QUALITY EVALUATION = "Como esse resultado foi avaliado?"

    Entidade separada de DecisionRecord e ExecutionResult.
    Não recalcula score — persiste exatamente o quality_score do JudgeResult.
    """
    id: str
    execution_result_id: str

    quality_score: float      # 0.0 a 1.0 — exatamente o score do JudgeResult
    passed: bool              # quality_score >= policy.pass_threshold
    evaluator: str            # ex: "rule_based", "code", "llm", "human", "composite"
    reason: str               # explicação legível do resultado

    criteria: Optional[dict] = None      # scores por critério (ex: {"correctness": 0.9})
    metadata: Optional[dict] = None      # extensível: weights, threshold, etc.

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.criteria is None:
            object.__setattr__(self, "criteria", {})
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
