"""Executions service — puro Python, sem depender de FastAPI."""

from typing import Optional
from olympus.db.interfaces import RepositorioPersistencia


def listar_execucoes(
    repo: RepositorioPersistencia,
    limit: int = 50,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    return repo.listar_execucoes(limit=limit, project_id=project_id, status=status)


def obter_execucao(repo: RepositorioPersistencia, execution_id: str) -> Optional[dict]:
    return repo.obter_execucao(execution_id)
