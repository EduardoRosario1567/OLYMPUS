from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from olympus.services.executions_service import listar_execucoes, obter_execucao
from app.core.deps import get_repo, usuario_autenticado
from app.schemas.executions import ExecucaoOut, ExecucaoDetalheOut

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("", response_model=list[ExecucaoOut])
def listar(
    limit: int = Query(default=50, ge=1, le=200),
    project_id: Optional[str] = Query(default=None),
    status_filtro: Optional[str] = Query(default=None, alias="status"),
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
) -> list[ExecucaoOut]:
    return listar_execucoes(repo, limit=limit, project_id=project_id, status=status_filtro)


@router.get("/{execution_id}", response_model=ExecucaoDetalheOut)
def obter(
    execution_id: str,
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
) -> ExecucaoDetalheOut:
    execucao = obter_execucao(repo, execution_id)
    if execucao is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada.")
    return execucao
