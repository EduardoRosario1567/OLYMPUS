import os
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.core.deps import identidade_autenticada
from olympus.memory import build_memory_store, MemoryWriter, MemoryContextProvider, MemoryType, Sensitivity, MemoryStatus

ROOT=Path(__file__).resolve().parents[3]
_STORE=build_memory_store(
    os.environ.get('OLYMPUS_MEMORY_DATABASE_URL')
    or os.environ.get('OLYMPUS_MEMORY_DB', str(ROOT/'olympus_memory.db'))
)
_WRITER=MemoryWriter(_STORE)
_CONTEXT=MemoryContextProvider(_STORE)
router=APIRouter(prefix='/memory',tags=['memory'])
class CreateMemory(BaseModel):
    type: MemoryType; key:str; value:Dict[str,Any]; sensitivity:Sensitivity=Sensitivity.LOW; project_id:Optional[str]=None
class UpdateMemory(BaseModel):
    key:Optional[str]=None; value:Optional[Dict[str,Any]]=None; sensitivity:Optional[Sensitivity]=None; status:Optional[MemoryStatus]=None

def view(m):
    return {'id':m.id,'type':m.type,'key':m.key,'value':m.value,'sensitivity':m.sensitivity,'status':m.status,'project_id':m.project_id,'source':m.source,'created_at':m.created_at,'updated_at':m.updated_at}
@router.get('')
def list_memory(type:Optional[MemoryType]=None,project_id:Optional[str]=None,identity=Depends(identidade_autenticada)):
    return {'memories':[view(m) for m in _STORE.list(identity.tenant_id,identity.user_id,project_id,type)]}

@router.get('/context')
def memory_context(
    task: str = Query(..., min_length=1, max_length=12000),
    project_id: Optional[str] = Query(default=None, max_length=128),
    identity=Depends(identidade_autenticada),
):
    """Return only confirmed, relevant context for the current identity.

    This is the provider-neutral boundary later consumed by the MCP bridge.
    It never exposes another tenant/user scope and keeps prompt growth bounded
    inside MemoryContextProvider.
    """
    context = _CONTEXT.relevant(task, identity.tenant_id, identity.user_id, project_id)
    return {
        'context': context,
        'has_context': bool(context),
        'project_id': project_id,
        'scope': {'tenant_id': identity.tenant_id, 'user_id': identity.user_id},
    }
@router.post('',status_code=201)
def create_memory(payload:CreateMemory,identity=Depends(identidade_autenticada)):
    try:return view(_WRITER.propose(identity.tenant_id,identity.user_id,payload.type,payload.key,payload.value,payload.sensitivity,payload.project_id,'api'))
    except PermissionError as e: raise HTTPException(422,str(e))
@router.patch('/{memory_id}')
def update_memory(memory_id:str,payload:UpdateMemory,identity=Depends(identidade_autenticada)):
    m=_STORE.update(memory_id,identity.tenant_id,identity.user_id,**payload.model_dump(exclude_none=True))
    if m is None: raise HTTPException(404,'memory not found')
    return view(m)
@router.delete('/{memory_id}',status_code=204)
def delete_memory(memory_id:str,identity=Depends(identidade_autenticada)):
    if not _STORE.delete(memory_id,identity.tenant_id,identity.user_id): raise HTTPException(404,'memory not found')
