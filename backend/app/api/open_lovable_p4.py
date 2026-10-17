"""OLYMPUS authenticated Open Lovable P4 experiment: NO runtime execution.

Uses existing JWT, organization RBAC, and cloud project ownership.
Feature opt-in is single-host development only; no model or sandbox calls.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import identidade_com_permissao
from app.core.open_lovable_p4_store import (
    ReservationStore, ReservationMissing, ReservationConflict,
)

router = APIRouter(prefix="/cloud/open-lovable", tags=["open-lovable-experimental"])
_read = identidade_com_permissao("projects.read")
_run = identidade_com_permissao("missions.run")


class ReservationRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    client_request_id: str = Field(min_length=12, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


def _lab_only() -> None:
    if os.environ.get("OLYMPUS_OPEN_LOVABLE_P4") != "1":
        raise HTTPException(status_code=503, detail="OPEN_LOVABLE_P4_DISABLED")
    if os.environ.get("OLYMPUS_ENV", "development").strip().lower() in ("prod", "production"):
        raise HTTPException(status_code=503, detail="OPEN_LOVABLE_P4_PRODUCTION_NOT_QUALIFIED")
    if os.environ.get("OLYMPUS_DB_BACKEND", "sqlite").strip().lower() == "postgres":
        raise HTTPException(status_code=503, detail="OPEN_LOVABLE_P4_SQLITE_LAB_ONLY")


def _store() -> ReservationStore:
    path = os.environ.get("OLYMPUS_OPEN_LOVABLE_P4_DB")
    if not path:
        data = Path(os.environ.get("OLYMPUS_CLOUD_DATA_DIR", ".olympus/cloud"))
        path = str(data / "integrations" / "open-lovable-p4.sqlite3")
    return ReservationStore(path)


def _check_project(project_id: str, tenant_id: str) -> None:
    from app.api.cloud_runtime import _RUNTIME
    project = _RUNTIME.projects.get(project_id)
    if project is None or project.tenant_id != tenant_id:
        # Do not leak cross-tenant project existence.
        raise HTTPException(status_code=404, detail="project not found")


@router.get("/status")
def status(identity=Depends(_read)):
    _lab_only()
    return {
        "status": "POLICY_ONLY",
        "tenant_scoped": True,
        "user_scoped": True,
        "free_model_verified": False,
        "sandbox_attested": False,
        "model_calls": 0,
        "execution_available": False,
    }


@router.post("/reservations", status_code=201)
def reserve(payload: ReservationRequest, identity=Depends(_run)):
    _lab_only()
    _check_project(payload.project_id, identity.tenant_id)
    try:
        return _store().create(
            tenant_id=identity.tenant_id, actor_id=identity.user_id,
            project_id=payload.project_id, client_request_id=payload.client_request_id
        )
    except ReservationConflict:
        raise HTTPException(status_code=409, detail="POLICY_RESERVATION_CONFLICT")


@router.get("/reservations/{reservation_id}")
def inspect(reservation_id: str, identity=Depends(_read)):
    _lab_only()
    try:
        return _store().owner_view(
            reservation_id=reservation_id, tenant_id=identity.tenant_id,
            actor_id=identity.user_id
        )
    except ReservationMissing:
        raise HTTPException(status_code=404, detail="reservation not found")


@router.post("/reservations/{reservation_id}/block")
def block(reservation_id: str, identity=Depends(_run)):
    _lab_only()
    try:
        return _store().block(
            reservation_id=reservation_id, tenant_id=identity.tenant_id,
            actor_id=identity.user_id
        )
    except ReservationMissing:
        raise HTTPException(status_code=404, detail="reservation not found")


@router.post("/reservations/{reservation_id}/execute", status_code=503)
def execute_forbidden(reservation_id: str, identity=Depends(_run)):
    # Always reject. No forwarding to upstream Open Lovable.
    _lab_only()
    try:
        _store().owner_view(reservation_id=reservation_id,
                            tenant_id=identity.tenant_id, actor_id=identity.user_id)
    except ReservationMissing:
        raise HTTPException(status_code=404, detail="reservation not found")
    raise HTTPException(status_code=503, detail="OPEN_LOVABLE_LIVE_EXECUTION_NOT_QUALIFIED")
