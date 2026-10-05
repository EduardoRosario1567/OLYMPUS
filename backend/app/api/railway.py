from dataclasses import asdict
from pathlib import Path
from typing import Optional
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import identidade_com_permissao
from app.core.saas import PLATFORM
from olympus.saas.platform import EntitlementError
from olympus.cloud.deployment import DeploymentPolicyError, DeploymentRequest, build_deployment_artifact
from olympus.cloud.railway_provider import RailwayApiError
from .cloud_runtime import _DEPLOYMENTS, _DEPLOYMENT_SECRETS, _GITHUB, _RAILWAY, _RUNTIME


router = APIRouter(prefix="/cloud/railway", tags=["cloud-railway"])
_can_deploy = identidade_com_permissao("deployments.manage")
_REVISION = re.compile(r"^[a-fA-F0-9]{7,64}$")


class RailwayConnect(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class RailwayLink(BaseModel):
    railway_project_id: str = Field(min_length=1, max_length=128)
    service_id: str = Field(min_length=1, max_length=128)
    environment_id: str = Field(min_length=1, max_length=128)
    repository: str = Field(min_length=3, max_length=201)


class SecretWrite(BaseModel):
    value: str = Field(min_length=1, max_length=65536)


class DeploymentCreate(BaseModel):
    environment: str = Field(default="production", pattern="^(preview|production)$")
    domain: Optional[str] = Field(default=None, max_length=253)


class DeploymentRollback(BaseModel):
    deployment_id: str = Field(min_length=1, max_length=128)
    target_deployment_id: str = Field(min_length=1, max_length=128)
    environment: str = Field(default="production", pattern="^(preview|production)$")


class DomainConfigure(BaseModel):
    deployment_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=3, max_length=253)
    environment: str = Field(default="production", pattern="^(preview|production)$")


def _view(value):
    return asdict(value) if value is not None else None


def _raise_safe(exc: Exception) -> None:
    if isinstance(exc, RailwayApiError):
        if exc.status == 401:
            raise HTTPException(status_code=401, detail="A conexão com o Railway expirou ou não possui acesso.")
        if exc.status == 409:
            raise HTTPException(status_code=409, detail=str(exc))
        if exc.status >= 500:
            raise HTTPException(status_code=503, detail="O Railway está temporariamente indisponível.")
        raise HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'"))
    if isinstance(exc, (ValueError, DeploymentPolicyError)):
        raise HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, EntitlementError):
        raise HTTPException(status_code=402, detail=str(exc))
    raise exc


def _ensure_idle(project_id: str, tenant_id: str) -> None:
    if _RUNTIME.project_is_busy(project_id, tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de publicar.")


@router.post("/connection")
def connect(payload: RailwayConnect, identity=Depends(_can_deploy)):
    try:
        return {"connected": True, "account": _RAILWAY.connect(identity.tenant_id, payload.token)}
    except Exception as exc:
        _raise_safe(exc)


@router.delete("/connection", status_code=204)
def disconnect(identity=Depends(_can_deploy)):
    _RAILWAY.disconnect(identity.tenant_id)


@router.get("/projects/{project_id}")
def status(project_id: str, identity=Depends(_can_deploy)):
    try:
        value = _RAILWAY.status(project_id, identity.tenant_id)
        return {"connected": value["account"] is not None, "account": value["account"], "binding": _view(value["binding"]),
                "deployments": [_view(item) for item in _DEPLOYMENTS.list(identity.tenant_id, project_id, "production")]}
    except Exception as exc:
        _raise_safe(exc)


@router.put("/projects/{project_id}/service")
def link(project_id: str, payload: RailwayLink, identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    try:
        _RUNTIME.projects.project_root(project_id, tenant_id=identity.tenant_id)
        return _view(_RAILWAY.link(project_id, identity.tenant_id, payload.railway_project_id,
                                   payload.service_id, payload.environment_id, payload.repository))
    except Exception as exc:
        _raise_safe(exc)


@router.delete("/projects/{project_id}/service", status_code=204)
def unlink(project_id: str, identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    if not _RAILWAY.unlink(project_id, identity.tenant_id):
        raise HTTPException(status_code=404, detail="Projeto ainda não está conectado ao Railway.")


@router.get("/projects/{project_id}/secrets")
def list_secrets(project_id: str, environment: str = "production", identity=Depends(_can_deploy)):
    try:
        _RUNTIME.projects.project_root(project_id, tenant_id=identity.tenant_id)
        return {"secrets": [_view(item) for item in _DEPLOYMENT_SECRETS.list(identity.tenant_id, project_id, environment)]}
    except Exception as exc:
        _raise_safe(exc)


@router.put("/projects/{project_id}/secrets/{name}")
def put_secret(project_id: str, name: str, payload: SecretWrite, environment: str = "production", identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    try:
        _RUNTIME.projects.project_root(project_id, tenant_id=identity.tenant_id)
        return _view(_DEPLOYMENT_SECRETS.put(identity.tenant_id, project_id, environment, name, payload.value))
    except Exception as exc:
        _raise_safe(exc)


@router.delete("/projects/{project_id}/secrets/{name}", status_code=204)
def delete_secret(project_id: str, name: str, environment: str = "production", identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    try:
        if not _DEPLOYMENT_SECRETS.delete(identity.tenant_id, project_id, environment, name):
            raise KeyError("Segredo não encontrado.")
    except Exception as exc:
        _raise_safe(exc)


@router.post("/projects/{project_id}/deployments", status_code=202)
def deploy(project_id: str, payload: DeploymentCreate, identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    tenant_id = identity.tenant_id
    reserved = False
    try:
        PLATFORM.consume(tenant_id, identity.user_id, "deployments_month")
        reserved = True
        PLATFORM.record_action(tenant_id, identity.user_id, "deployment.requested", "project", project_id, {"provider": "railway", "environment": payload.environment})
        project_root = _RUNTIME.projects.project_root(project_id, tenant_id=tenant_id)
        github = _GITHUB.status(project_id, tenant_id).get("binding")
        railway = _RAILWAY.status(project_id, tenant_id).get("binding")
        if github is None or railway is None:
            raise DeploymentPolicyError("Conecte o mesmo projeto ao GitHub e ao Railway antes de publicar.")
        if "%s/%s" % (github.owner, github.repo) != railway.repository:
            raise DeploymentPolicyError("GitHub e Railway apontam para repositórios diferentes.")
        synchronized = _GITHUB.sync(project_id, tenant_id, "Olympus: versão aprovada para publicação")
        revision = str(synchronized.commit_sha or "").strip()
        if not _REVISION.fullmatch(revision):
            raise DeploymentPolicyError("Sincronize o projeto com o GitHub antes de publicar.")
        versions = _RUNTIME.versions.list(project_id, tenant_id=tenant_id)
        if not versions:
            raise DeploymentPolicyError("Crie uma versão do projeto antes de publicar.")
        references = _DEPLOYMENT_SECRETS.list(tenant_id, project_id, payload.environment)
        artifacts = Path(_RUNTIME.data_dir, "deployments", tenant_id, project_id)
        artifacts.mkdir(parents=True, exist_ok=True)
        artifact = build_deployment_artifact(project_root, artifacts / (uuid.uuid4().hex + ".zip"),
                                             environment=payload.environment, secret_references=references)
        request = DeploymentRequest(tenant_id, project_id, versions[0].version_id, payload.environment,
                                    artifact, references, payload.domain, revision)
        result = _DEPLOYMENTS.deploy("railway", request)
        if payload.domain:
            result = _DEPLOYMENTS.configure_domain(tenant_id, project_id, payload.environment, "railway", result.deployment_id, payload.domain)
        return _view(result)
    except Exception as exc:
        if reserved:
            PLATFORM.refund(tenant_id, identity.user_id, "deployments_month")
        _raise_safe(exc)


@router.post("/projects/{project_id}/rollback", status_code=202)
def rollback(project_id: str, payload: DeploymentRollback, identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    try:
        return _view(_DEPLOYMENTS.rollback(identity.tenant_id, project_id, payload.environment, "railway",
                                           payload.deployment_id, payload.target_deployment_id))
    except Exception as exc:
        _raise_safe(exc)


@router.post("/projects/{project_id}/domain")
def domain(project_id: str, payload: DomainConfigure, identity=Depends(_can_deploy)):
    _ensure_idle(project_id, identity.tenant_id)
    try:
        return _view(_DEPLOYMENTS.configure_domain(identity.tenant_id, project_id, payload.environment,
                                                   "railway", payload.deployment_id, payload.domain))
    except Exception as exc:
        _raise_safe(exc)
