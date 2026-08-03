"""Logs service — puro Python, sem depender de FastAPI."""

from typing import Optional
from olympus.db.interfaces import RepositorioPersistencia


def listar_logs(
    repo: RepositorioPersistencia,
    limit: int = 50,
    project_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    level: Optional[str] = None,
    busca: Optional[str] = None,
) -> list[dict]:
    return repo.listar_logs(
        limit=limit, project_id=project_id, execution_id=execution_id, level=level, busca=busca
    )
