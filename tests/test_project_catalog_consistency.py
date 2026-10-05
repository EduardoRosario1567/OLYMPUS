"""A05: API writes must agree with later reads, writes and process restart."""
import json
from pathlib import Path
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from olympus.cloud.project_workspace import ProjectWorkspaceManager

@pytest.fixture
def api():
    from app.main import app
    from app.api import cloud_runtime
    from app.core.saas import PLATFORM
    from app.core.tenancy import identity_for
    from app.core.security import emitir_token
    suffix=uuid.uuid4().hex
    owner=identity_for('catalog-owner-'+suffix+'@olympus.test')
    other=identity_for('catalog-other-'+suffix+'@olympus.test')
    for identity in (owner,other):
        PLATFORM.bootstrap_owner(identity.user_id,identity.email,identity.tenant_id)
    headers={role:{'Authorization':'Bearer '+emitir_token(identity.email,identity.tenant_id)}
             for role,identity in [('owner',owner),('other',other)]}
    with TestClient(app,raise_server_exceptions=False) as client:
        yield client,cloud_runtime,owner,headers

def create(api, name='Original'):
    client,runtime,owner,headers=api
    pid='catalog-'+uuid.uuid4().hex[:12]
    response=client.post('/cloud/projects',headers=headers['owner'],json={'project_id':pid,'name':name})
    assert response.status_code==201,response.text
    root=Path(runtime._RUNTIME.projects.get(pid).root)
    (root/'marker.txt').write_text('PRESERVED_PROJECT')
    return pid,root

def names(api):
    client,_,_,headers=api
    response=client.get('/cloud/projects?limit=10000',headers=headers['owner'])
    assert response.status_code==200,response.text
    return {row['project_id']:row['name'] for row in response.json()['projects']}

def test_rename_is_immediately_visible_in_list_and_detail(api):
    pid,root=create(api);client,runtime,owner,headers=api
    result=client.patch('/cloud/projects/'+pid,headers=headers['owner'],json={'name':'  Novo nome  '})
    assert result.status_code==200,result.text
    assert names(api)[pid]=='Novo nome'
    detail=client.get('/cloud/projects/'+pid,headers=headers['owner'])
    assert detail.status_code==200
    assert detail.json()['name']=='Novo nome'
    assert (root/'marker.txt').read_text()=='PRESERVED_PROJECT'

def test_future_create_cannot_overwrite_rename_and_restart_keeps_name(api):
    pid,_=create(api);client,runtime,owner,headers=api
    assert client.patch('/cloud/projects/'+pid,headers=headers['owner'],json={'name':'Durável'}).status_code==200
    create(api,'Outro')
    restarted=ProjectWorkspaceManager(str(runtime._RUNTIME.data_dir))
    assert restarted.get(pid).name=='Durável'
    assert names(api)[pid]=='Durável'

def test_deleted_project_disappears_from_list_and_detail(api):
    pid,_=create(api);client,_,_,headers=api
    assert client.delete('/cloud/projects/'+pid,headers=headers['owner']).status_code==204
    assert pid not in names(api)
    assert client.get('/cloud/projects/'+pid,headers=headers['owner']).status_code==404

def test_future_create_cannot_resurrect_deleted_project_and_archive_keeps_history(api):
    pid,root=create(api);client,runtime,owner,headers=api
    (root/'.executions').mkdir();(root/'.executions/history.txt').write_text('PRESERVED_HISTORY')
    assert client.delete('/cloud/projects/'+pid,headers=headers['owner']).status_code==204
    create(api,'Outro')
    restarted=ProjectWorkspaceManager(str(runtime._RUNTIME.data_dir))
    assert restarted.get(pid) is None
    assert not root.exists()
    archived=list((runtime._RUNTIME.data_dir/'project-trash').glob('*'+pid))
    assert len(archived)==1
    assert (archived[0]/'marker.txt').read_text()=='PRESERVED_PROJECT'
    assert (archived[0]/'.executions/history.txt').read_text()=='PRESERVED_HISTORY'

def test_foreign_tenant_rename_preserves_catalog_and_project(api):
    pid,root=create(api);client,runtime,_,headers=api
    catalog=runtime._RUNTIME.projects.index_path;before=catalog.read_bytes()
    response=client.patch('/cloud/projects/'+pid,headers=headers['other'],json={'name':'Intruso'})
    assert response.status_code==404
    assert catalog.read_bytes()==before
    assert names(api)[pid]=='Original'
    assert (root/'marker.txt').read_text()=='PRESERVED_PROJECT'

def test_invalid_rename_leaves_persisted_and_visible_state_unchanged(api):
    pid,_=create(api);client,runtime,_,headers=api
    catalog=runtime._RUNTIME.projects.index_path;before=catalog.read_bytes()
    response=client.patch('/cloud/projects/'+pid,headers=headers['owner'],json={'name':'  '})
    assert response.status_code==400
    assert catalog.read_bytes()==before
    assert names(api)[pid]=='Original'

def test_busy_project_cannot_be_deleted(api):
    pid,root=create(api);client,runtime,owner,headers=api
    runtime._RUNTIME.store.create(pid,'synthetic-mission','Synthetic task',tenant_id=owner.tenant_id,user_id=owner.user_id)
    response=client.delete('/cloud/projects/'+pid,headers=headers['owner'])
    assert response.status_code==409
    assert names(api)[pid]=='Original'
    assert (root/'marker.txt').read_text()=='PRESERVED_PROJECT'

def test_rename_write_failure_leaves_memory_and_disk_unchanged(api):
    from olympus.cloud import project_catalog
    pid,_=create(api);client,runtime,_,headers=api
    catalog=runtime._RUNTIME.projects.index_path;before=catalog.read_bytes()
    with patch.object(project_catalog.os,'replace',side_effect=OSError('synthetic write failure')):
        response=client.patch('/cloud/projects/'+pid,headers=headers['owner'],json={'name':'Falhou'})
    assert response.status_code==500
    assert catalog.read_bytes()==before
    assert names(api)[pid]=='Original'

def test_delete_write_failure_restores_archived_directory_and_catalog(api):
    from olympus.cloud import project_catalog
    pid,root=create(api);client,runtime,_,headers=api
    catalog=runtime._RUNTIME.projects.index_path;before=catalog.read_bytes()
    with patch.object(project_catalog.os,'replace',side_effect=OSError('synthetic write failure')):
        response=client.delete('/cloud/projects/'+pid,headers=headers['owner'])
    assert response.status_code==500
    assert catalog.read_bytes()==before
    assert names(api)[pid]=='Original'
    assert (root/'marker.txt').read_text()=='PRESERVED_PROJECT'

def test_each_catalog_change_preserves_a_distinct_recoverable_backup(api):
    from olympus.cloud import project_catalog
    pid,_=create(api);client,runtime,_,headers=api
    catalog=runtime._RUNTIME.projects.index_path
    existing=set(catalog.parent.glob('projects.json.bak-v305-*'))
    with patch.object(project_catalog.time,'strftime',return_value='20000101_000000'):
        assert client.patch('/cloud/projects/'+pid,headers=headers['owner'],json={'name':'Alterado'}).status_code==200
        assert client.delete('/cloud/projects/'+pid,headers=headers['owner']).status_code==204
    backups=set(catalog.parent.glob('projects.json.bak-v305-*'))-existing
    assert len(backups)==2
    assert {json.loads(p.read_text())[pid]['name'] for p in backups}=={'Original','Alterado'}
