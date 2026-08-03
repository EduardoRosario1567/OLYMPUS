"""
Dependências injetadas nas rotas: registry, repositório e o usuário autenticado.
Backend escolhido via OLYMPUS_DB_BACKEND=sqlite|postgres (default: sqlite,
porque é o único validado de verdade neste momento — ver ressalva no repo).
"""

import os
from pathlib import Path
from fastapi import Header, HTTPException, status

from olympus.registry import ModelRegistry
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from app.core.seed import seed_models
from app.core.security import validar_token

# backend/app/core/deps.py -> parents[2] é a raiz do repo (contém backend/ e olympus/ como irmãos).
# Ancorado em __file__ em vez de relativo ao CWD: antes, "olympus_dev.db" resolvia
# diferente dependendo de onde o processo era iniciado — backend e scripts/seed_demo.py
# podiam acabar gravando em arquivos diferentes sem nenhum erro visível.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SQLITE_PATH = str(_REPO_ROOT / "olympus_dev.db")

_registry: ModelRegistry | None = None
_repo = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = seed_models(ModelRegistry())
    return _registry


def get_repo():
    global _repo
    if _repo is None:
        backend = os.environ.get("OLYMPUS_DB_BACKEND", "sqlite")
        if backend == "postgres":
            # TODO: montar Session real (SQLAlchemy) e usar PostgresRepository(session).
            # Não habilitado por padrão: não foi validado contra um Postgres real ainda.
            raise NotImplementedError(
                "Backend 'postgres' ainda não tem a Session real conectada aqui. "
                "Use PostgresRepository(session) manualmente até isso ser fechado."
            )
        db_path = os.environ.get("OLYMPUS_SQLITE_PATH", _DEFAULT_SQLITE_PATH)
        _repo = SQLiteDevRepository(db_path)
    return _repo


def usuario_autenticado(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente.")
    token = authorization.removeprefix("Bearer ").strip()
    email = validar_token(token)
    if email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")
    return email
