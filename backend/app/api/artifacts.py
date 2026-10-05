import base64, os
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.core.deps import identidade_com_permissao
from olympus.artifacts import ArtifactStore, ArtifactType

ROOT=Path(__file__).resolve().parents[3]
_STORE=ArtifactStore(os.environ.get('OLYMPUS_ARTIFACT_DB',str(ROOT/'olympus_artifacts.db')),os.environ.get('OLYMPUS_ARTIFACT_ROOT',str(ROOT/'.olympus'/'artifacts')))
router=APIRouter(prefix='/artifacts',tags=['artifacts'])
_can_read = identidade_com_permissao('projects.read')
_can_write = identidade_com_permissao('projects.write')
class CreateArtifact(BaseModel):
    project_id:str; mission_id:str; execution_id:str; type:ArtifactType; name:str; content_base64:str; metadata:Dict[str,Any]={}
def view(a):
    return {'id':a.id,'project_id':a.project_id,'mission_id':a.mission_id,'execution_id':a.execution_id,'type':a.type,'name':a.name,'size_bytes':a.size_bytes,'version':a.version,'metadata':a.metadata,'sha256':a.sha256,'created_at':a.created_at}
@router.get('')
def list_artifacts(project_id:Optional[str]=None,mission_id:Optional[str]=None,identity=Depends(_can_read)):
    return {'artifacts':[view(a) for a in _STORE.list(identity.tenant_id,project_id,mission_id)]}
@router.post('',status_code=201)
def create_artifact(payload:CreateArtifact,identity=Depends(_can_write)):
    try: content=base64.b64decode(payload.content_base64,validate=True)
    except Exception: raise HTTPException(422,'invalid base64 content')
    try:return view(_STORE.create(identity.tenant_id,payload.project_id,payload.mission_id,payload.execution_id,payload.type,payload.name,content,payload.metadata))
    except ValueError as e: raise HTTPException(422,str(e))
@router.get('/{artifact_id}')
def get_artifact(artifact_id:str,identity=Depends(_can_read)):
    a=_STORE.get(artifact_id,identity.tenant_id)
    if not a:raise HTTPException(404,'artifact not found')
    return view(a)
@router.get('/{artifact_id}/download')
def download_artifact(artifact_id:str,identity=Depends(_can_read)):
    a=_STORE.get(artifact_id,identity.tenant_id); p=_STORE.content_path(artifact_id,identity.tenant_id)
    if not a or not p:raise HTTPException(404,'artifact not found')
    return FileResponse(str(p),filename=a.name,media_type=a.metadata.get('content_type','application/octet-stream'))
@router.delete('/{artifact_id}',status_code=204)
def delete_artifact(artifact_id:str,identity=Depends(_can_write)):
    if not _STORE.delete(artifact_id,identity.tenant_id):raise HTTPException(404,'artifact not found')
