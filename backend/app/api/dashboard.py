"""
Router de dashboard — só o resumo agregado.

Execuções e logs recentes NÃO têm rota própria aqui: o dashboard consome
GET /executions e GET /logs (mesmos endpoints da tela cheia), só que com
limit menor. Duas rotas separadas pra a mesma pergunta ("quais as
execuções/logs recentes?") era duplicação real — schemas divergentes pra
um dado idêntico. Removido na consolidação da Alpha.
"""

from fastapi import APIRouter, Depends

from olympus.services.dashboard_service import montar_dashboard_summary
from app.core.deps import get_registry, get_repo, usuario_autenticado
from app.schemas.dashboard import DashboardSummaryResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    _usuario: str = Depends(usuario_autenticado),
    registry=Depends(get_registry),
    repo=Depends(get_repo),
) -> DashboardSummaryResponse:
    resumo = montar_dashboard_summary(repo, registry)
    return DashboardSummaryResponse(
        total_execucoes=resumo.total_execucoes,
        total_modelos=resumo.total_modelos,
        total_projetos=resumo.projetos.valor or 0,
        custo_total=resumo.custo_total,
        latencia_media_ms=resumo.latencia_media_ms,
        taxa_sucesso=resumo.taxa_sucesso,
        fallback_rate=resumo.fallback_rate,
        total_decisoes=resumo.total_decisoes,
        modelo_mais_usado=resumo.modelo_mais_usado,
        agentes_implementado=resumo.agentes.implementado,
    )
