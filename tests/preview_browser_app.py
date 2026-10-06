"""Local-only browser fixture: real API and sessions, controlled container."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.api import cloud_projects
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.project_studio import ProjectRuntimeManager
from olympus.cloud.project_workspace import ProjectWorkspaceManager
from tests.test_preview_sessions import ControlledContainerExecutor

temporary=tempfile.TemporaryDirectory(prefix='olympus-browser-fixture-')
projects=ProjectWorkspaceManager(temporary.name)
payload=b'''<html><body><main>OPAQUE_PREVIEW</main><script>
let parentBlocked=false,storageBlocked=false;
try{parent.localStorage.getItem('PARENT_SECRET')}catch{parentBlocked=true}
try{localStorage.getItem('PARENT_SECRET')}catch{storageBlocked=true}
fetch('/forbidden').then(()=>parent.postMessage({type:'probe',parentBlocked,storageBlocked,connectBlocked:false},'*'))
.catch(()=>parent.postMessage({type:'probe',parentBlocked,storageBlocked,connectBlocked:true},'*'));
</script><script type="module" src="/probe.mjs"></script></body></html>'''
module=b"parent.postMessage({type:'module',loaded:true},'*');"

class BrowserExecutor(ControlledContainerExecutor):
    def fetch(self,handle,target='/',query=''):
        if target=='/probe.mjs':return 200,{'Content-Type':'application/javascript'},module
        return 200,{'Content-Type':'text/html'},payload

record=projects.create('Runtime fixture','runtime',tenant_id='fixture')
Path(record.root,'package.json').write_text(json.dumps({'scripts':{'dev':'next dev'},'dependencies':{'next':'1'}}))
static=projects.create('Static fixture','static',tenant_id='fixture')
Path(static.root,'index.html').write_bytes(payload);Path(static.root,'probe.mjs').write_bytes(module)
manager=ProjectRuntimeManager(projects,executor=BrowserExecutor())
cloud_projects._STUDIO_RUNTIMES=manager
cloud_projects._RUNTIME=SimpleNamespace(projects=projects)
cloud_projects._PREVIEWS=ProjectPreviewSessions(projects)

@asynccontextmanager
async def lifespan(app):
    yield
    manager.close();temporary.cleanup()

app=FastAPI(lifespan=lifespan);app.include_router(cloud_projects.router)
identity=SimpleNamespace(tenant_id='fixture')
app.dependency_overrides[cloud_projects._can_read]=lambda:identity
forbidden_requests=0

@app.get('/parent')
def parent():
    runtime=cloud_projects.create_preview_session('runtime',identity)['preview_url']
    static_url=cloud_projects.create_preview_session('static',identity)['preview_url']
    source=(Path(__file__).resolve().parents[1]/'frontend/app/missao/page.tsx').read_text()
    flags=re.findall(r'sandbox="([^"]+)"',source)
    assert flags==['allow-scripts','allow-scripts']
    return HTMLResponse('''<html><body data-private="PARENT_ONLY"><script>
localStorage.setItem('PARENT_SECRET','SYNTHETIC_PARENT_ONLY');window.probes=[];window.modules=[];
addEventListener('message',e=>{if(e.data.type==='probe')probes.push({...e.data,origin:e.origin});
if(e.data.type==='module')modules.push(e.data)});
</script>'''+f'<iframe sandbox="{flags[0]}" src="{runtime}"></iframe>'
        +f'<iframe sandbox="allow-scripts allow-same-origin" src="{runtime}"></iframe>'
        +f'<iframe sandbox="{flags[1]}" src="{static_url}"></iframe></body></html>')

@app.get('/forbidden')
def forbidden():
    global forbidden_requests
    forbidden_requests+=1
    return {'unexpected':True}

@app.get('/stats')
def stats():return {'forbidden_requests':forbidden_requests}
