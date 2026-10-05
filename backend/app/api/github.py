from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import identidade_com_permissao
from olympus.cloud.github_integration import GitHubApiError
from .cloud_runtime import _GITHUB, _RUNTIME


router = APIRouter(prefix="/cloud/github", tags=["cloud-github"])
_can_deploy = identidade_com_permissao("deployments.manage")


class GitHubConnect(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class RepositoryCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    repo: str = Field(min_length=1, max_length=100)
    private: bool = False


class RepositoryLink(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    branch: Optional[str] = Field(default=None, max_length=128)


class BranchCreate(BaseModel):
    branch: str = Field(min_length=1, max_length=128)


class RepositorySync(BaseModel):
    message: str = Field(default="Atualização pelo Olympus", max_length=200)


def _view(value):
    return asdict(value) if value is not None else None


def _status(project_id: str, tenant_id: str):
    value = _GITHUB.status(project_id, tenant_id)
    return {"connected": value["account"] is not None, "account": _view(value["account"]), "repository": _view(value["binding"])}


def _raise_safe(exc: Exception) -> None:
    if isinstance(exc, GitHubApiError):
        if exc.status == 404:
            raise HTTPException(status_code=404, detail="Repositório ou recurso não encontrado no GitHub.")
        if exc.status in {409, 422}:
            raise HTTPException(status_code=409, detail=str(exc))
        if exc.status >= 500:
            raise HTTPException(status_code=503, detail="O GitHub está temporariamente indisponível.")
        raise HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc).strip("'"))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("/connection")
def connect(payload: GitHubConnect, identity=Depends(_can_deploy)):
    try:
        account = _GITHUB.connect(identity.tenant_id, payload.token)
        return {"connected": True, "account": _view(account)}
    except Exception as exc:
        _raise_safe(exc)


@router.delete("/connection", status_code=204)
def disconnect(identity=Depends(_can_deploy)):
    _GITHUB.disconnect(identity.tenant_id)


@router.get("/projects/{project_id}")
def project_status(project_id: str, identity=Depends(_can_deploy)):
    try:
        return _status(project_id, identity.tenant_id)
    except Exception as exc:
        _raise_safe(exc)


@router.post("/repositories", status_code=201)
def create_repository(payload: RepositoryCreate, identity=Depends(_can_deploy)):
    if _RUNTIME.project_is_busy(payload.project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de conectar o GitHub.")
    try:
        binding = _GITHUB.create_repository(payload.project_id, identity.tenant_id, payload.repo, payload.private)
        return _view(binding)
    except Exception as exc:
        _raise_safe(exc)


@router.put("/projects/{project_id}/repository")
def link_repository(project_id: str, payload: RepositoryLink, identity=Depends(_can_deploy)):
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de conectar o GitHub.")
    try:
        return _view(_GITHUB.link_repository(project_id, identity.tenant_id, payload.owner, payload.repo, payload.branch))
    except Exception as exc:
        _raise_safe(exc)


@router.delete("/projects/{project_id}/repository", status_code=204)
def unlink_repository(project_id: str, identity=Depends(_can_deploy)):
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de remover o vínculo.")
    try:
        if not _GITHUB.unlink_repository(project_id, identity.tenant_id):
            raise KeyError("Projeto ainda não está conectado a um repositório.")
    except Exception as exc:
        _raise_safe(exc)


@router.post("/projects/{project_id}/branches", status_code=201)
def create_branch(project_id: str, payload: BranchCreate, identity=Depends(_can_deploy)):
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de criar uma branch.")
    try:
        return _view(_GITHUB.create_branch(project_id, identity.tenant_id, payload.branch))
    except Exception as exc:
        _raise_safe(exc)


@router.post("/projects/{project_id}/sync")
def sync_repository(project_id: str, payload: RepositorySync, identity=Depends(_can_deploy)):
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de sincronizar.")
    try:
        return _view(_GITHUB.sync(project_id, identity.tenant_id, payload.message))
    except Exception as exc:
        _raise_safe(exc)


@router.get("/projects/{project_id}/commits")
def list_commits(project_id: str, limit: int = Query(default=20, ge=1, le=50), identity=Depends(_can_deploy)):
    try:
        return {"commits": _GITHUB.commits(project_id, identity.tenant_id, limit)}
    except Exception as exc:
        _raise_safe(exc)


@router.post("/projects/{project_id}/publish")
def publish(project_id: str, identity=Depends(_can_deploy)):
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de publicar.")
    try:
        return _view(_GITHUB.publish(project_id, identity.tenant_id))
    except Exception as exc:
        _raise_safe(exc)


@router.get("/projects/{project_id}/publication")
def publication(project_id: str, identity=Depends(_can_deploy)):
    try:
        return _GITHUB.publication_status(project_id, identity.tenant_id)
    except Exception as exc:
        _raise_safe(exc)
