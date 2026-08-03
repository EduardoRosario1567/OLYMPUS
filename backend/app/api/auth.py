from fastapi import APIRouter, HTTPException, status

from app.schemas.dashboard import LoginRequest, LoginResponse
from app.core.security import autenticar

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    token = autenticar(payload.email, payload.senha)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")
    return LoginResponse(access_token=token)
