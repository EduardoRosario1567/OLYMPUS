import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import identidade_com_permissao
from olympus.media.higgsfield import HiggsfieldClient, HiggsfieldError

router = APIRouter(prefix="/media", tags=["media"])
_can_run = identidade_com_permissao("missions.run")


class HiggsfieldGenerate(BaseModel):
    model_path: str = Field(min_length=2, max_length=300)
    parameters: Dict[str, Any]
    paid_authorized: bool = False
    spend_cap_usd: float = Field(default=0.0, ge=0, le=1000)
    project_id: Optional[str] = Field(default=None, max_length=128)
    mission_id: Optional[str] = Field(default=None, max_length=128)


def _paid_gate(payload: HiggsfieldGenerate):
    # Higgsfield is a paid/external media provider. The provider's API does
    # not expose a universal per-request price in this boundary, so Olympus
    # refuses an unbounded call and reports that the account controls billing.
    if not payload.paid_authorized:
        raise HTTPException(status_code=402, detail="A geração Higgsfield exige autorização explícita.")
    if payload.spend_cap_usd <= 0:
        raise HTTPException(status_code=400, detail="Informe um teto positivo para a geração Higgsfield.")


@router.get("/higgsfield/configuration")
def higgsfield_configuration(_identity=Depends(_can_run)):
    return {
        "provider": "higgsfield",
        "configured": bool(os.environ.get("HIGGSFIELD_API_KEY_ID") and os.environ.get("HIGGSFIELD_API_KEY_SECRET")),
        "mode": "paid_authorization_required",
        "api": "official_async",
    }


@router.post("/higgsfield/generations", status_code=202)
def generate_higgsfield(payload: HiggsfieldGenerate, _identity=Depends(_can_run)):
    _paid_gate(payload)
    try:
        result = HiggsfieldClient().submit(payload.model_path, payload.parameters)
    except HiggsfieldError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "provider": "higgsfield",
        "status": result.get("status", "queued"),
        "request_id": result.get("request_id"),
        "status_url": result.get("status_url"),
        "cancel_url": result.get("cancel_url"),
        "project_id": payload.project_id,
        "mission_id": payload.mission_id,
        "billing": {"authorized": True, "spend_cap_usd": payload.spend_cap_usd},
    }


@router.get("/higgsfield/generations/{request_id}")
def higgsfield_status(request_id: str, _identity=Depends(_can_run)):
    try:
        return HiggsfieldClient().status(request_id)
    except HiggsfieldError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/higgsfield/generations/{request_id}/cancel")
def higgsfield_cancel(request_id: str, _identity=Depends(_can_run)):
    try:
        return HiggsfieldClient().cancel(request_id)
    except HiggsfieldError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
