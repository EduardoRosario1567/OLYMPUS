from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.dashboard import LoginRequest, LoginResponse
from app.core.security import autenticar, limpar_falhas_login, registrar_falha_login

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    client = request.client.host if request.client else "unknown"
    key = "%s:%s" % (client, payload.email.strip().lower())
    if registrar_falha_login(key):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde um minuto antes de tentar novamente.")
    token = autenticar(payload.email, payload.senha)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")
    limpar_falhas_login(key)
    return LoginResponse(access_token=token)
