import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from olympus.cloud.preview_container import PreviewContainerExecutor, PreviewLifecycleError
from olympus.cloud.project_studio import ProjectRuntimeManager, PreviewStopError
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class ControlledContainerExecutor(PreviewContainerExecutor):
    """Only the container boundary is controlled; manager/API remain real."""
    def __init__(self):
        super().__init__()
        self.handles=[];self.starts=[];self.stops=[];self.requests=[]
        self.responses=[];self.fail_cleanup=False;self.fail_http=False
        self.log_entries=[];self.log_requests=[];self.fail_logs=False

    def logs(self,handle):
        self.log_requests.append(handle.name)
        if self.fail_logs:raise PreviewLifecycleError('fixture logs unavailable',handle)
        return self.log_entries

    def start(self,root,framework,package_path='.'):
        handle=SimpleNamespace(name='fixture-'+str(len(self.starts)),status='container_running',cleanup_confirmed=False)
        self.starts.append((root,framework,package_path));self.handles.append(handle)
        return handle

    def running(self,handle):
        return any(h is handle for h in self.handles) and handle.status=='container_running'

    def stop(self,handle):
        if self.fail_cleanup:
            handle.status='cleanup_unconfirmed';return False
        self.stops.append(handle.name);handle.status='stopped';handle.cleanup_confirmed=True
        self.handles=[h for h in self.handles if h is not handle]
        return True

    def pending(self):
        return tuple(h for h in self.handles if h.status=='cleanup_unconfirmed')

    def fetch(self,handle,target='/',query=''):
        self.requests.append((handle.name,target,query))
        if self.fail_http:raise PreviewLifecycleError('fixture HTTP unavailable',handle)
        if self.responses:return self.responses.pop(0)
        if target=='/logo.png':return 200,{'Content-Type':'image/png'},b'\x00\xffASSET'
        return 200,{'Content-Type':'text/html'},b'<html><body><main>SESSION_FIXTURE</main><img src="/logo.png"></body></html>'


class PreviewSessionFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.projects=ProjectWorkspaceManager(self.tmp.name)
        self.project=self.projects.create('Web','web',tenant_id='tenant-a')
        self.root=Path(self.project.root)
        (self.root/'package.json').write_text(json.dumps({'scripts':{'dev':'next dev'},'dependencies':{'next':'1'}}))
        self.executor=ControlledContainerExecutor()
        self.manager=ProjectRuntimeManager(self.projects,executor=self.executor,startup_timeout_seconds=0.05)
        self.addCleanup(self.close)

    def close(self):
        self.executor.fail_cleanup=False;self.manager.close()


class PreviewSessionIntegrationTests(PreviewSessionFixture):
    def test_start_confirms_http_reuses_session_and_scopes_assets(self):
        first=self.manager.start('web','tenant-a');second=self.manager.start('web','tenant-a')
        self.assertEqual(first.token,second.token)
        self.assertEqual(first.status,'running');self.assertIsNone(first.process);self.assertEqual(first.port,0)
        self.assertEqual(len(self.executor.starts),1)
        status,headers,body=self.manager.proxy(first.token)
        self.assertEqual(status,200)
        self.assertIn(('/cloud/projects/_runtime/'+first.token+'/logo.png').encode(),body)
        self.assertIn(b'olympus-element-selected',body)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.manager.proxy(first.token,'logo.png')[2],b'\x00\xffASSET')
        self.assertTrue(self.manager.logs('web','tenant-a'))

    def test_readiness_failure_removes_container_and_publishes_no_session(self):
        self.executor.fail_http=True
        with self.assertRaisesRegex(RuntimeError,'HTTP'):self.manager.start('web','tenant-a')
        self.assertEqual(self.manager._sessions,{})
        self.assertEqual(self.executor.handles,[])

    def test_non_html_readiness_is_rejected(self):
        self.executor.responses=[(200,{'Content-Type':'image/png'},b'not HTML')]*10
        with self.assertRaisesRegex(RuntimeError,'HTTP'):self.manager.start('web','tenant-a')
        self.assertEqual(self.executor.handles,[])

    def test_failed_cleanup_retains_budget_and_reports_state(self):
        session=self.manager.start('web','tenant-a');self.executor.fail_cleanup=True
        with self.assertRaises(PreviewStopError):self.manager.stop_checked('web','tenant-a')
        self.assertEqual(self.manager.get('web','tenant-a').status,'cleanup_unconfirmed')
        with self.assertRaisesRegex(RuntimeError,'remoção'):self.manager.start('web','tenant-a')
        self.assertEqual(len(self.executor.starts),1)
        self.executor.fail_cleanup=False
        self.assertTrue(self.manager.stop_checked('web','tenant-a'))
        self.assertNotIn(session.token,self.manager._sessions)

    def test_expiration_revokes_capability_and_stops_container(self):
        session=self.manager.start('web','tenant-a');session.expires_at=0
        with self.assertRaises(KeyError):self.manager.proxy(session.token)
        self.assertEqual(self.executor.handles,[])
        self.assertIsNone(self.manager.get('web','tenant-a'))

    def test_expiration_sweep_stops_idle_container(self):
        session=self.manager.start('web','tenant-a');session.expires_at=0
        self.manager._expire_sessions()
        self.assertEqual(self.executor.handles,[])

    def test_project_owner_checked_before_container_operations(self):
        with self.assertRaises(KeyError):self.manager.start('web','tenant-b')
        self.assertEqual(self.executor.starts,[])

    def test_concurrent_requests_create_only_one_container(self):
        with ThreadPoolExecutor(max_workers=5) as workers:
            sessions=list(workers.map(lambda _:self.manager.start('web','tenant-a'),range(5)))
        self.assertEqual(len({s.token for s in sessions}),1)
        self.assertEqual(len(self.executor.starts),1)

    def test_capacity_rejects_second_project_before_creation(self):
        self.manager.max_active=1;self.manager.start('web','tenant-a')
        project=self.projects.create('Other','other',tenant_id='tenant-a')
        (Path(project.root)/'package.json').write_bytes((self.root/'package.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError,'limite'):self.manager.start('other','tenant-a')
        self.assertEqual(len(self.executor.starts),1)

    def test_redirects_are_scoped_and_external_destinations_are_omitted(self):
        session=self.manager.start('web','tenant-a')
        for location,expected in [('/inside','/inside'),('http://127.0.0.1:3000/inside','/inside'),('https://external.test',None),('//external.test',None)]:
            with self.subTest(location=location):
                self.executor.responses=[(302,{'Content-Type':'text/html','Location':location},b'')]
                _,headers,_=self.manager.proxy(session.token)
                if expected:self.assertEqual(headers['Location'],'/cloud/projects/_runtime/'+session.token+expected)
                else:self.assertNotIn('Location',headers)

    def test_shutdown_removes_container_and_rejects_new_start(self):
        self.manager.start('web','tenant-a');self.manager.close()
        self.assertEqual(self.executor.handles,[])
        with self.assertRaisesRegex(RuntimeError,'encerrado'):self.manager.start('web','tenant-a')


class PreviewAPIFixture(PreviewSessionFixture):
    def setUp(self):
        super().setUp()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import cloud_projects,cloud_runtime
        self.identity=SimpleNamespace(tenant_id='tenant-a')
        app=FastAPI();app.include_router(cloud_projects.router);app.include_router(cloud_runtime.router)
        for dependency in [cloud_projects._can_read,cloud_projects._can_write,cloud_runtime._can_run]:
            app.dependency_overrides[dependency]=lambda:self.identity
        runtime=SimpleNamespace(projects=self.projects,project_is_busy=lambda *args:False)
        for module in [cloud_projects,cloud_runtime]:
            for name,value in [('_STUDIO_RUNTIMES',self.manager),('_RUNTIME',runtime)]:
                current=patch.object(module,name,value);current.start();self.addCleanup(current.stop)
        self.client=TestClient(app);self.addCleanup(self.client.close)


class PreviewAPIIntegrationTests(PreviewAPIFixture):
    def test_api_creates_serves_status_logs_and_revokes_session(self):
        created=self.client.post('/cloud/projects/web/preview-session')
        self.assertEqual(created.status_code,201,created.text)
        self.assertEqual(created.json()['kind'],'runtime')
        url=created.json()['preview_url']
        page=self.client.get(url);self.assertEqual(page.status_code,200)
        self.assertIn('SESSION_FIXTURE',page.text)
        self.assertIn('sandbox allow-scripts',page.headers['content-security-policy'])
        self.assertEqual(self.client.get(url+'logo.png').content,b'\x00\xffASSET')
        self.assertEqual(self.client.get('/cloud/projects/web/runtime').json()['status'],'running')
        self.assertTrue(self.client.get('/cloud/projects/web/runtime/logs').json())
        self.assertEqual(self.client.delete('/cloud/projects/web/runtime').status_code,204)
        self.assertEqual(self.client.get(url).status_code,404)

    def test_api_cleanup_failure_reports_conflict_and_preserves_project(self):
        created=self.client.post('/cloud/projects/web/preview-session');url=created.json()['preview_url']
        self.executor.fail_cleanup=True
        result=self.client.delete('/cloud/projects/web/runtime')
        self.assertEqual(result.status_code,409,result.text)
        state=self.client.get('/cloud/projects/web/runtime').json()
        self.assertEqual(state['status'],'cleanup_unconfirmed');self.assertIsNone(state['preview_url'])
        self.assertEqual(self.client.get(url).status_code,404)
        deleted=self.client.delete('/cloud/projects/web')
        self.assertEqual(deleted.status_code,409,deleted.text)
        self.assertIsNotNone(self.projects.get('web'));self.assertTrue((self.root/'package.json').exists())

    def test_api_unready_service_publishes_no_capability(self):
        self.executor.fail_http=True
        result=self.client.post('/cloud/projects/web/preview-session')
        self.assertEqual(result.status_code,409,result.text)
        self.assertNotIn('preview_url',result.json())
        self.assertEqual(self.manager._sessions,{})

    def test_api_other_tenant_has_no_container_effect(self):
        self.identity=SimpleNamespace(tenant_id='tenant-b')
        self.assertEqual(self.client.post('/cloud/projects/web/preview-session').status_code,404)
        self.assertEqual(self.client.delete('/cloud/projects/web/runtime').status_code,404)
        self.assertEqual(self.executor.starts,[]);self.assertEqual(self.executor.stops,[])

if __name__=='__main__':unittest.main()
