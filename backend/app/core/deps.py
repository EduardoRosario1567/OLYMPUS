import os
from pathlib import Path
from typing import Optional
from fastapi import Header, HTTPException, status

from olympus.registry import ModelRegistry
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from app.core.seed import seed_models
from app.core.security import validar_identity
from app.core.tenancy import Identity
from app.core.saas import PLATFORM
from olympus.saas.platform import AuthorizationError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SQLITE_PATH = str(_REPO_ROOT / "olympus_dev.db")
_registry = None
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
            raise NotImplementedError("Backend 'postgres' ainda não tem Session real conectada aqui.")
        db_path = os.environ.get("OLYMPUS_SQLITE_PATH", _DEFAULT_SQLITE_PATH)
        _repo = SQLiteDevRepository(db_path)
    return _repo


def identidade_autenticada(authorization: Optional[str] = Header(default=None)) -> Identity:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente.")
    token = authorization.removeprefix("Bearer ").strip()
    ident = validar_identity(token)
    if ident is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")
    return ident


def usuario_autenticado(authorization: Optional[str] = Header(default=None)) -> str:
    return identidade_autenticada(authorization).email


def identidade_com_permissao(permission: str):
    def dependency(authorization: Optional[str] = Header(default=None)) -> Identity:
        identity = identidade_autenticada(authorization)
        try:
            PLATFORM.authorize(identity.tenant_id, identity.user_id, permission)
        except AuthorizationError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não possui permissão para esta ação.")
        return identity
    return dependency
