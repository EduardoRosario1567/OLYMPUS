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
