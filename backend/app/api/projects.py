from fastapi import APIRouter, Depends, HTTPException, Query, status

from olympus.services.projects_service import listar_projetos, obter_projeto
from app.core.deps import get_repo, usuario_autenticado
from app.schemas.projects import ProjetoOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjetoOut])
def listar(
    limit: int = Query(default=50, ge=1, le=200),
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
) -> list[ProjetoOut]:
    return listar_projetos(repo, limit=limit)


@router.get("/{project_id}", response_model=ProjetoOut)
def obter(
    project_id: str,
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
) -> ProjetoOut:
    projeto = obter_projeto(repo, project_id)
    if projeto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return projeto


@router.get("/{project_id}/executions", response_model=list)
def execucoes_do_projeto(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
):
    from olympus.services.executions_service import listar_execucoes
    return listar_execucoes(repo, limit=limit, project_id=project_id)


@router.get("/{project_id}/logs", response_model=list)
def logs_do_projeto(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
):
    from olympus.services.logs_service import listar_logs
    return listar_logs(repo, limit=limit, project_id=project_id)
