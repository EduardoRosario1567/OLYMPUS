from typing import Optional

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
    modelo_principal: Optional[str] = None
    confianca_media: Optional[float] = None
    fallback_usado: Optional[bool] = None


class ExecucaoDetalheOut(BaseModel):
    id: str
    project_id: str
    status: str
    total_cost: float
    total_latency_ms: int
    success_count: int
    fallback_count: int
    created_at: str
    result_summary: Optional[str]
