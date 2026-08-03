from pydantic import BaseModel


class ExecucaoOut(BaseModel):
    id: str
    project_id: str
    status: str
    total_cost: float
    total_latency_ms: int
    success_count: int
    fallback_count: int
    created_at: str
    modelo_principal: str | None = None
    confianca_media: float | None = None
    fallback_usado: bool | None = None


class ExecucaoDetalheOut(BaseModel):
    id: str
    project_id: str
    status: str
    total_cost: float
    total_latency_ms: int
    success_count: int
    fallback_count: int
    created_at: str
    result_summary: str | None
