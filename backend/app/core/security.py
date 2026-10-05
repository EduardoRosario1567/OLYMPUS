import os
import time
import hmac
import threading
from typing import Optional

import jwt

from app.core.tenancy import identity_for, Identity
from app.core.saas import PLATFORM

_DEVELOPMENT_SECRET = "dev-secret-troque-em-producao-0123456789abcdef0123456789"
SECRET_KEY = os.environ.get("OLYMPUS_JWT_SECRET", _DEVELOPMENT_SECRET)
ALGORITHM = "HS256"
EXPIRA_EM_SEGUNDOS = 60 * 60 * 8

ADMIN_EMAIL = os.environ.get("OLYMPUS_ADMIN_EMAIL", "admin@olympus.local")
ADMIN_SENHA = os.environ.get("OLYMPUS_ADMIN_SENHA")

_LOGIN_LOCK = threading.Lock()
_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_WINDOW_SECONDS = 60.0
_LOGIN_MAX_FAILURES = 8


def registrar_falha_login(chave: str) -> bool:
    """Return whether the key is temporarily blocked after repeated failures."""
    now = time.time()
    with _LOGIN_LOCK:
        tentativas = [item for item in _LOGIN_FAILURES.get(chave, ()) if now - item < _LOGIN_WINDOW_SECONDS]
        tentativas.append(now)
        _LOGIN_FAILURES[chave] = tentativas
        return len(tentativas) > _LOGIN_MAX_FAILURES


def limpar_falhas_login(chave: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(chave, None)


def validar_configuracao_producao() -> None:
    if os.environ.get("OLYMPUS_ENV", "development").strip().lower() not in {"production", "prod"}:
        return
    if SECRET_KEY == _DEVELOPMENT_SECRET or len(SECRET_KEY) < 32:
        raise RuntimeError("OLYMPUS_JWT_SECRET forte é obrigatório em produção.")
    if os.environ.get("OLYMPUS_DB_BACKEND", "sqlite").strip().lower() != "postgres":
        raise RuntimeError("Produção exige OLYMPUS_DB_BACKEND=postgres; SQLite é somente local.")
    password = os.environ.get("OLYMPUS_ADMIN_SENHA")
    if password is not None and len(password) < 12:
        raise RuntimeError("OLYMPUS_ADMIN_SENHA deve ter ao menos 12 caracteres em produção.")


def emitir_token(email: str, tenant_id: str) -> str:
    ident = identity_for(email)
    now = int(time.time())
    payload = {
        "sub": ident.user_id,
        "email": ident.email,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + EXPIRA_EM_SEGUNDOS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def autenticar(email: str, senha: str) -> Optional[str]:
    account = PLATFORM.authenticate(email, senha)
    if account is not None:
        user_id, organization_id = account
        expected = identity_for(email)
        if user_id != expected.user_id:
            return None
        return emitir_token(expected.email, organization_id)
    admin_email = os.environ.get("OLYMPUS_ADMIN_EMAIL", ADMIN_EMAIL)
    admin_senha = os.environ.get("OLYMPUS_ADMIN_SENHA", ADMIN_SENHA)
    if admin_senha is None:
        raise RuntimeError(
            "OLYMPUS_ADMIN_SENHA não configurada. Defina a variável de ambiente "
            "antes de subir o backend."
        )
    if not hmac.compare_digest(email.strip().lower(), admin_email.strip().lower()) or not hmac.compare_digest(senha, admin_senha):
        return None
    ident = identity_for(email)
    PLATFORM.bootstrap_owner(ident.user_id, ident.email, ident.tenant_id)
    return emitir_token(ident.email, ident.tenant_id)


def validar_identity(token: str) -> Optional[Identity]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("sub")
        if not email or not tenant_id or not user_id:
            return None
        expected = identity_for(str(email))
        if expected.user_id != user_id or PLATFORM.role_for(str(tenant_id), str(user_id)) is None:
            return None
        return Identity(expected.user_id, expected.email, str(tenant_id))
    except jwt.PyJWTError:
        return None


def validar_token(token: str) -> Optional[str]:
    ident = validar_identity(token)
    return ident.email if ident else None
