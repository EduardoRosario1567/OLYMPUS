from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Optional
import mimetypes
from urllib.parse import quote

from app.core.deps import identidade_com_permissao
from app.core.saas import PLATFORM
from olympus.saas.platform import EntitlementError
from olympus.cloud.attachments import AttachmentTooLarge, MAX_ATTACHMENT_BYTES
from .cloud_runtime import _ATTACHMENTS, _FILES, _PREVIEWS, _RUNTIME, _STUDIO_RUNTIMES

router = APIRouter(prefix="/cloud/projects", tags=["cloud-projects"])
_can_read = identidade_com_permissao("projects.read")
_can_write = identidade_com_permissao("projects.write")

class ProjectCreate(BaseModel):
    project_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)

class ProjectVersionCreate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=100)

class ProjectVersionRestore(BaseModel):
    confirm: bool = False

class ProjectFileSave(BaseModel):
    content: str = Field(max_length=1024 * 1024)
    expected_sha256: str = Field(min_length=64, max_length=64)

def _view(record):
    return {
        "project_id": record.project_id,
        "name": record.name,
        "tenant_id": record.tenant_id,
        "root": None,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }

def _attachment_view(record):
    return {
        "attachment_id": record.attachment_id,
        "project_id": record.project_id,
        "name": record.name,
        "content_type": record.content_type,
        "size": record.size,
        "kind": record.kind,
        "created_at": record.created_at,
    }

def _version_view(record):
    return {
        "version_id": record.version_id,
        "project_id": record.project_id,
        "label": record.label,
        "reason": record.reason,
        "created_at": record.created_at,
        "file_count": record.file_count,
        "size_bytes": record.size_bytes,
        "execution_id": record.execution_id,
    }

def _file_view(record):
    return {
        "path": record.path,
        "size": record.size,
        "sha256": record.sha256,
        "updated_at": record.updated_at,
    }

def _runtime_view(record, include_url: bool = True):
    if record is None:
        return {"status": "stopped", "framework": None, "preview_url": None, "error": None}
    return {
        "status": record.status,
        "framework": record.framework,
        "preview_url": "/cloud/projects/_runtime/%s/" % record.token if include_url and record.status == "running" else None,
        "error": record.error,
        "started_at": record.started_at,
        "expires_at": record.expires_at,
    }

@router.post("", status_code=201)
def create(payload: ProjectCreate, identity=Depends(_can_write)):
    try:
        current = len(_RUNTIME.projects.list(10000, tenant_id=identity.tenant_id))
        PLATFORM.assert_capacity(identity.tenant_id, "projects", current + 1)
        PLATFORM.record_action(identity.tenant_id, identity.user_id, "project.create_requested", "project", payload.project_id or "generated", {"name": payload.name})
        project = _RUNTIME.projects.create(payload.name, payload.project_id, tenant_id=identity.tenant_id)
        return _view(project)
    except EntitlementError as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

@router.get("")
def list_projects(limit: int = 100, identity=Depends(_can_read)):
    return {"projects": [_view(item) for item in _RUNTIME.projects.list(limit, tenant_id=identity.tenant_id)]}

@router.get("/{project_id}/download")
def download_project(project_id: str, identity=Depends(_can_read)):
    try:
        project = _RUNTIME.projects.get(project_id)
        if project is None or project.tenant_id != identity.tenant_id:
            raise HTTPException(status_code=404, detail="project not found")
        archive = _RUNTIME.projects.export_zip(project_id, tenant_id=identity.tenant_id)
        return FileResponse(
            str(archive),
            filename=archive.name,
            media_type="application/zip",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="project not found")

@router.post("/{project_id}/attachments", status_code=201)
async def upload_attachment(
    project_id: str,
    request: Request,
    filename: str = Query(min_length=1, max_length=180),
    content_type: Optional[str] = Header(default=None),
    content_length: Optional[int] = Header(default=None),
    identity=Depends(_can_write),
):
    if content_length is not None and content_length > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo excede o limite de 20 MB.")
    try:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_ATTACHMENT_BYTES:
                raise AttachmentTooLarge("attachment exceeds 20 MB")
            body.extend(chunk)
        record = _ATTACHMENTS.save(
            project_id,
            filename,
            bytes(body),
            content_type=content_type,
            tenant_id=identity.tenant_id,
        )
        return _attachment_view(record)
    except AttachmentTooLarge:
        raise HTTPException(status_code=413, detail="O arquivo excede o limite permitido.")
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/{project_id}/attachments")
def list_attachments(project_id: str, identity=Depends(_can_read)):
    try:
        return {"attachments": [_attachment_view(item) for item in _ATTACHMENTS.list(project_id, tenant_id=identity.tenant_id)]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

@router.get("/{project_id}/files")
def list_files(project_id: str, identity=Depends(_can_read)):
    try:
        return {"files": [_file_view(item) for item in _FILES.list(project_id, tenant_id=identity.tenant_id)]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

@router.get("/{project_id}/file")
def read_file(project_id: str, path: str = Query(min_length=1, max_length=500), identity=Depends(_can_read)):
    try:
        record, content = _FILES.read(project_id, path, tenant_id=identity.tenant_id)
        return {**_file_view(record), "content": content}
    except KeyError:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Este arquivo não pode ser aberto com segurança.")

@router.put("/{project_id}/file")
def save_file(project_id: str, payload: ProjectFileSave, path: str = Query(min_length=1, max_length=500), identity=Depends(_can_write)):
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de editar arquivos.")
    try:
        record, backup = _FILES.save(project_id, path, payload.content, payload.expected_sha256, tenant_id=identity.tenant_id)
        return {**_file_view(record), "content": payload.content, "safety_backup": _version_view(backup)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    except RuntimeError:
        raise HTTPException(status_code=409, detail="Este arquivo mudou desde que foi aberto. Recarregue antes de salvar.")
    except ValueError:
        raise HTTPException(status_code=400, detail="A alteração não pôde ser aplicada com segurança.")

@router.delete("/{project_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(project_id: str, attachment_id: str, identity=Depends(_can_write)):
    try:
        if not _ATTACHMENTS.delete(project_id, attachment_id, tenant_id=identity.tenant_id):
            raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

@router.get("/{project_id}/versions")
def list_versions(project_id: str, limit: int = Query(default=50, ge=1, le=100), identity=Depends(_can_read)):
    try:
        return {"versions": [_version_view(item) for item in _RUNTIME.versions.list(project_id, tenant_id=identity.tenant_id)[:limit]]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

@router.post("/{project_id}/versions", status_code=201)
def create_version(project_id: str, payload: ProjectVersionCreate, identity=Depends(_can_write)):
    try:
        return _version_view(_RUNTIME.versions.capture(project_id, label=payload.label, reason="manual", tenant_id=identity.tenant_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except ValueError:
        raise HTTPException(status_code=409, detail="O projeto contém um item que não pode ser versionado com segurança.")

@router.get("/{project_id}/versions/{version_id}/compare")
def compare_version(
    project_id: str,
    version_id: str,
    against: Optional[str] = Query(default=None, max_length=64),
    identity=Depends(_can_read),
):
    try:
        return _RUNTIME.versions.compare(project_id, version_id, against_version_id=against, tenant_id=identity.tenant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto ou versão não encontrados.")
    except ValueError:
        raise HTTPException(status_code=409, detail="A versão não pôde ser comparada com segurança.")

@router.post("/{project_id}/versions/{version_id}/restore")
def restore_version(project_id: str, version_id: str, payload: ProjectVersionRestore, identity=Depends(_can_write)):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirme a restauração para continuar.")
    try:
        _STUDIO_RUNTIMES.stop(project_id, identity.tenant_id)
        restored, safety = _RUNTIME.restore_project_version(project_id, version_id, tenant_id=identity.tenant_id)
        return {"restored": _version_view(restored), "safety_backup": _version_view(safety)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto ou versão não encontrados.")
    except ValueError:
        raise HTTPException(status_code=409, detail="A versão falhou na verificação de integridade e não foi aplicada.")
    except RuntimeError:
        raise HTTPException(status_code=409, detail="Aguarde a missão atual terminar antes de restaurar uma versão.")

@router.post("/{project_id}/preview-session", status_code=201)
def create_preview_session(project_id: str, identity=Depends(_can_read)):
    try:
        runtime_info = _STUDIO_RUNTIMES.detect(project_id, tenant_id=identity.tenant_id)
        if runtime_info["kind"] == "runtime":
            runtime = _STUDIO_RUNTIMES.start(project_id, tenant_id=identity.tenant_id)
            return {
                "preview_url": "/cloud/projects/_runtime/%s/" % runtime.token,
                "entrypoint": runtime.framework,
                "expires_at": runtime.expires_at,
                "kind": "runtime",
                "status": runtime.status,
            }
        session = _PREVIEWS.create(project_id, tenant_id=identity.tenant_id)
        return {
            "preview_url": "/cloud/projects/_preview/%s/%s" % (session.token, quote(session.entrypoint, safe="/")),
            "entrypoint": session.entrypoint,
            "expires_at": session.expires_at,
            "kind": "static",
            "status": "running",
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except ValueError:
        raise HTTPException(status_code=409, detail="Este projeto ainda não possui uma página web compatível para visualizar.")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.get("/{project_id}/runtime")
def runtime_status(project_id: str, identity=Depends(_can_read)):
    try:
        _RUNTIME.projects.project_root(project_id, tenant_id=identity.tenant_id)
        return _runtime_view(_STUDIO_RUNTIMES.get(project_id, identity.tenant_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

@router.get("/{project_id}/runtime/logs")
def runtime_logs(project_id: str, after: int = Query(default=0, ge=0), identity=Depends(_can_read)):
    try:
        logs = _STUDIO_RUNTIMES.logs(project_id, identity.tenant_id, after=after)
        return {"logs": [{"seq": item.seq, "at": item.at, "stream": item.stream, "message": item.message} for item in logs]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

@router.delete("/{project_id}/runtime", status_code=204)
def stop_runtime(project_id: str, identity=Depends(_can_write)):
    try:
        _RUNTIME.projects.project_root(project_id, tenant_id=identity.tenant_id)
        _STUDIO_RUNTIMES.stop(project_id, identity.tenant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

def _preview_response(token: str, asset_path: Optional[str] = None):
    try:
        session, path = _PREVIEWS.resolve(token, asset_path)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Preview indisponível ou expirado.")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'self'",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    if path.suffix.lower() in {".html", ".htm", ".css"}:
        content = path.read_text(encoding="utf-8", errors="replace")
        content = _PREVIEWS.rewrite_text(session.token, path.suffix.lower(), content)
        return Response(content=content, media_type=media_type, headers=headers)
    return FileResponse(str(path), media_type=media_type, headers=headers)

@router.get("/_preview/{token}", include_in_schema=False)
def preview_entry(token: str):
    return _preview_response(token)

@router.get("/_preview/{token}/{asset_path:path}", include_in_schema=False)
def preview_asset(token: str, asset_path: str):
    return _preview_response(token, asset_path or None)

def _runtime_response(token: str, request: Request, asset_path: str = ""):
    try:
        status, headers, content = _STUDIO_RUNTIMES.proxy(token, asset_path, request.url.query)
        return Response(content=content, status_code=status, headers=headers)
    except (KeyError, ValueError, OSError):
        raise HTTPException(status_code=404, detail="Preview executável indisponível ou expirado.")

@router.get("/_runtime/{token}/", include_in_schema=False)
def runtime_entry(token: str, request: Request):
    return _runtime_response(token, request)

@router.get("/_runtime/{token}/{asset_path:path}", include_in_schema=False)
def runtime_asset(token: str, asset_path: str, request: Request):
    return _runtime_response(token, request, asset_path)

@router.get("/{project_id}")
def get_project(project_id: str, identity=Depends(_can_read)):
    try:
        record = _RUNTIME.projects.get(project_id)
        if record is None or record.tenant_id != identity.tenant_id:
            raise HTTPException(status_code=404, detail="project not found")
        return _view(record)
    except KeyError:
        raise HTTPException(status_code=404, detail="project not found")
