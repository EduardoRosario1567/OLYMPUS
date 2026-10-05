from dataclasses import asdict
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from typing import Literal, Optional
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.core.deps import identidade_autenticada
from olympus.distribution import AccessDenied, RunnerRegistry, RunnerReleaseCatalog, RunnerUpdateError, SQLiteRunnerStateStore


def _signing_key() -> bytes:
    configured = os.environ.get("OLYMPUS_RUNNER_SIGNING_KEY")
    if configured is None:
        # Session-only local key: a backend restart safely invalidates all
        # credentials. Production must inject a stable key from its secret store.
        return secrets.token_bytes(32)
    payload = configured.encode("utf-8")
    if len(payload) < 32:
        raise RuntimeError("OLYMPUS_RUNNER_SIGNING_KEY must contain at least 32 bytes")
    return payload


_configured_signing_key = os.environ.get("OLYMPUS_RUNNER_SIGNING_KEY")
_runner_store = None
if _configured_signing_key is not None:
    _runner_data_dir = Path(os.environ.get("OLYMPUS_CLOUD_DATA_DIR", ".olympus/cloud"), "integrations")
    _runner_store = SQLiteRunnerStateStore(_runner_data_dir / "runner-registry.sqlite3")
_RUNNERS = RunnerRegistry(_signing_key(), state_store=_runner_store)
router = APIRouter(prefix="/cloud/runner", tags=["cloud-runner"])


class RunnerActivate(BaseModel):
    code: str = Field(min_length=20, max_length=256)
    installation_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    platform: Literal["linux", "macos", "windows"]
    runner_version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")


class RunnerRefresh(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


def _license_for(tenant_id: str) -> str:
    # The beta contract derives a non-secret, tenant-bound entitlement. The
    # billing milestone will replace this function with the subscription store.
    return "beta-" + sha256(tenant_id.encode("utf-8")).hexdigest()[:24]


def _credential_view(value):
    return {
        "installation_id": value.installation_id,
        "refresh_token": value.refresh_token,
        "access_token": value.access_token,
        "token_type": "bearer",
        "access_expires_at": value.access_expires_at,
    }


def _safe_access_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credencial do Runner inválida, expirada ou revogada.",
    )


@router.post("/enrollments", status_code=201)
def create_enrollment(identity=Depends(identidade_autenticada)):
    ticket = _RUNNERS.create_enrollment(identity.tenant_id, _license_for(identity.tenant_id))
    return {"code": ticket.code, "expires_at": ticket.expires_at}


@router.post("/activate", status_code=201)
def activate(payload: RunnerActivate):
    try:
        return _credential_view(
            _RUNNERS.activate(
                payload.code,
                payload.installation_id,
                platform=payload.platform,
                runner_version=payload.runner_version,
            )
        )
    except AccessDenied:
        raise _safe_access_error()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/token")
def rotate_token(payload: RunnerRefresh):
    try:
        return _credential_view(_RUNNERS.rotate(payload.refresh_token))
    except AccessDenied:
        raise _safe_access_error()


@router.get("/session")
def runner_session(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise _safe_access_error()


@router.get("/releases/latest")
def latest_release(
    platform: Literal["linux", "macos", "windows"],
    architecture: Literal["x86_64", "arm64"],
    current_version: str = Query(min_length=5, max_length=64, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$"),
    channel: Literal["stable", "beta"] = "stable",
    authorization: Optional[str] = Header(default=None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise _safe_access_error()
    try:
        _RUNNERS.verify(authorization.removeprefix("Bearer ").strip())
        release_dir_value = os.environ.get("OLYMPUS_RUNNER_RELEASE_DIR")
        public_key_value = os.environ.get("OLYMPUS_RUNNER_RELEASE_PUBLIC_KEY")
        if not release_dir_value or not public_key_value:
            raise HTTPException(status_code=503, detail="Canal de atualização do Runner ainda não está configurado.")
        catalog = RunnerReleaseCatalog(release_dir_value, public_key_value)
        verified = catalog.latest(platform=platform, architecture=architecture, channel=channel, current_version=current_version)
        return {
            "release": verified.release.payload(),
            "manifest_base64": b64encode(verified.canonical_manifest).decode("ascii"),
            "signature_base64": b64encode(verified.signature).decode("ascii"),
        }
    except HTTPException:
        raise
    except RunnerUpdateError as exc:
        if str(exc) == "Runner update is not newer than the installed version":
            return Response(status_code=204)
        raise HTTPException(status_code=503, detail="Nenhuma atualização íntegra está disponível.")
    except (AccessDenied, UnicodeError):
        raise _safe_access_error()
    except OSError:
        raise HTTPException(status_code=503, detail="Canal de atualização temporariamente indisponível.")
    try:
        claims = _RUNNERS.verify(authorization.removeprefix("Bearer ").strip())
        return asdict(claims)
    except (AccessDenied, UnicodeError):
        raise _safe_access_error()


@router.get("/installations")
def list_installations(identity=Depends(identidade_autenticada)):
    return {"installations": [asdict(item) for item in _RUNNERS.list_installations(identity.tenant_id)]}


@router.delete("/installations/{installation_id}")
def revoke_installation(installation_id: str, identity=Depends(identidade_autenticada)):
    try:
        return asdict(_RUNNERS.revoke(identity.tenant_id, installation_id))
    except AccessDenied:
        raise HTTPException(status_code=404, detail="Instalação do Runner não encontrada.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador de instalação inválido.")
