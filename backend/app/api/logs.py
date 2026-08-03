from fastapi import APIRouter, Depends, Query

from olympus.services.logs_service import listar_logs
from app.core.deps import get_repo, usuario_autenticado
from app.schemas.logs import LogOut

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[LogOut])
def listar(
    limit: int = Query(default=50, ge=1, le=200),
    project_id: str | None = Query(default=None),
    execution_id: str | None = Query(default=None),
    level: str | None = Query(default=None),
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
) -> list[LogOut]:
    return listar_logs(repo, limit=limit, project_id=project_id, execution_id=execution_id, level=level)


@router.get("/search", response_model=list[LogOut])
def buscar(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    _usuario: str = Depends(usuario_autenticado),
    repo=Depends(get_repo),
) -> list[LogOut]:
    return listar_logs(repo, limit=limit, busca=q)
