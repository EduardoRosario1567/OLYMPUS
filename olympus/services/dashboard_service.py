"""
Dashboard service — monta os payloads que a interface consome.
Puro Python: não depende de FastAPI, então é testável isoladamente.
A camada de API (backend/app/api/dashboard.py) só chama isso e serializa.

IMPORTANTE: "agentes" ainda não é entidade real no sistema — nunca foi
modelado. Em vez de inventar número, esse campo vem como None/0 com uma
flag `implementado=False`, pra interface exibir "pendente de modelagem"
honestamente em vez de um dado fantasma.

"projetos" JÁ é entidade real desde a Fase 2.2 (tabela projetos + FKs) —
esse campo usa o mesmo formato CardNaoImplementado por compatibilidade
com o schema existente, mas agora sempre vem com implementado=True e o
valor real.
"""

from dataclasses import dataclass, field
from typing import Optional

from olympus.db.interfaces import RepositorioPersistencia
from olympus.registry import ModelRegistry


@dataclass
class CardNaoImplementado:
    valor: Optional[int] = None
    implementado: bool = False


@dataclass
class DashboardSummary:
    total_execucoes: int
    total_modelos: int
    custo_total: float
    latencia_media_ms: float
    taxa_sucesso: float
    fallback_rate: float
    total_decisoes: int
    modelo_mais_usado: Optional[str]
    projetos: CardNaoImplementado = field(default_factory=CardNaoImplementado)
    agentes: CardNaoImplementado = field(default_factory=CardNaoImplementado)


def montar_dashboard_summary(repo: RepositorioPersistencia, registry: ModelRegistry) -> DashboardSummary:
    metricas = repo.resumo_metricas()
    total_modelos = len(registry.listar())
    total_projetos = len(repo.listar_projetos(limit=1000))

    return DashboardSummary(
        total_execucoes=metricas["total_execucoes"],
        total_modelos=total_modelos,
        custo_total=metricas["custo_total"],
        latencia_media_ms=metricas["latencia_media_ms"],
        taxa_sucesso=metricas["taxa_sucesso"],
        fallback_rate=metricas["fallback_rate"],
        total_decisoes=metricas["total_decisoes"],
        modelo_mais_usado=metricas["modelo_mais_usado"],
        projetos=CardNaoImplementado(valor=total_projetos, implementado=True),
    )
