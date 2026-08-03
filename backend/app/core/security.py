"""
Autenticação — versão provisória.

A Fase 1 não modelou a tabela `usuarios` (schema.sql cobre só
decisao_registros/execucoes/logs). Em vez de fingir que existe um sistema
de usuários completo, este módulo faz login contra UMA credencial de admin
vinda de variável de ambiente, emite um JWT de verdade, e deixa explícito
no código que isso precisa virar tabela `usuarios` + hash de senha real
antes de qualquer uso em produção com múltiplos usuários.
"""

import os
import time
from typing import Optional

import jwt  # PyJWT

SECRET_KEY = os.environ.get("OLYMPUS_JWT_SECRET", "dev-secret-troque-em-producao")
ALGORITHM = "HS256"
EXPIRA_EM_SEGUNDOS = 60 * 60 * 8  # 8h

ADMIN_EMAIL = os.environ.get("OLYMPUS_ADMIN_EMAIL", "admin@olympus.local")
ADMIN_SENHA = os.environ.get("OLYMPUS_ADMIN_SENHA")  # sem default: obriga configurar


def autenticar(email: str, senha: str) -> Optional[str]:
    """Retorna um JWT se as credenciais baterem, ou None caso contrário."""
    if ADMIN_SENHA is None:
        raise RuntimeError(
            "OLYMPUS_ADMIN_SENHA não configurada. Defina a variável de ambiente "
            "antes de subir o backend (TODO: substituir por tabela usuarios + hash real)."
        )
    if email != ADMIN_EMAIL or senha != ADMIN_SENHA:
        return None

    payload = {"sub": email, "exp": int(time.time()) + EXPIRA_EM_SEGUNDOS}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def validar_token(token: str) -> Optional[str]:
    """Retorna o email (sub) se o token for válido, ou None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
