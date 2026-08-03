"""Projects service — puro Python, sem depender de FastAPI."""

from typing import Optional
from olympus.db.interfaces import RepositorioPersistencia


def listar_projetos(repo: RepositorioPersistencia, limit: int = 50) -> list[dict]:
    return repo.listar_projetos(limit=limit)


def obter_projeto(repo: RepositorioPersistencia, project_id: str) -> Optional[dict]:
    return repo.obter_projeto(project_id)
