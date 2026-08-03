from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    senha: str
    lembrar: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DashboardSummaryResponse(BaseModel):
    total_execucoes: int
    total_modelos: int
    total_projetos: int
    custo_total: float
    latencia_media_ms: float
    taxa_sucesso: float
    fallback_rate: float
    total_decisoes: int
    modelo_mais_usado: str | None
    agentes_implementado: bool
