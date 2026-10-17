"""Regression cases: environment leakage, preview links, unauthorized effects, RBAC."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from olympus.agent.test_runner import TargetedTestRunner
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class TestRunnerEnvironment(unittest.TestCase):
    def run_source(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tests').mkdir();(root/'tests/__init__.py').write_text('')
            (root/'tests/test_environment.py').write_text(source)
            return TargetedTestRunner(tmp).run_unittest(['tests.test_environment'])

    def test_provider_jwt_proxy_and_arbitrary_variables_do_not_reach_test(self):
        source='import os,unittest\nclass T(unittest.TestCase):\n    def test_environment(self):\n        for key in '+repr(['GROQ_API_KEY','OLYMPUS_JWT_SECRET','HTTPS_PROXY','CUSTOM_PRIVATE_VALUE','PYTHONSTARTUP'])+':\n            self.assertNotIn(key,os.environ)\n'
        with patch.dict(os.environ,{key:'SYNTHETIC_MARKER' for key in ['GROQ_API_KEY','OLYMPUS_JWT_SECRET','HTTPS_PROXY','CUSTOM_PRIVATE_VALUE','PYTHONSTARTUP']}):
            result=self.run_source(source)
        self.assertTrue(result.success,result.stderr)

    def test_test_uses_active_python_environment(self):
        source='import sys,unittest\nclass T(unittest.TestCase):\n    def test_python(self):\n        self.assertEqual(sys.prefix,'+repr(sys.prefix)+')\n'
        result=self.run_source(source)
        self.assertTrue(result.success,result.stderr)

    def test_home_is_private_and_not_preserved_after_test(self):
        with tempfile.TemporaryDirectory() as original_home:
            source='import os,unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n    def test_home(self):\n        home=Path.home()\n        self.assertNotEqual(str(home),'+repr(original_home)+')\n        self.assertTrue(home.is_dir())\n        (home/"only-test.txt").write_text("test")\n        print("PRIVATE_HOME="+str(home))\n'
            with patch.dict(os.environ,{'HOME':original_home}):result=self.run_source(source)
            self.assertTrue(result.success,result.stderr)
            line=next(x for x in result.stdout.splitlines() if x.startswith('PRIVATE_HOME='))
            self.assertFalse(Path(line.split('=',1)[1]).exists())
            self.assertEqual(list(Path(original_home).iterdir()),[])


class TestPreviewLinks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.projects=ProjectWorkspaceManager(self.tmp.name)
        self.record=self.projects.create('Preview','preview',tenant_id='tenant-a');self.root=Path(self.record.root)
        (self.root/'index.html').write_text('<main>ok</main>')
        self.previews=ProjectPreviewSessions(self.projects);self.session=self.previews.create('preview','tenant-a')

    def reject(self, path):
        with self.assertRaises((KeyError,ValueError)):
            self.previews.resolve(self.session.token,path)

    def test_link_to_hidden_file_is_rejected(self):
        (self.root/'.env').write_text('SYNTHETIC_MARKER')
        (self.root/'linked.html').symlink_to(self.root/'.env');self.reject('linked.html')

    def test_link_to_allowed_file_is_rejected(self):
        (self.root/'linked.html').symlink_to(self.root/'index.html');self.reject('linked.html')

    def test_linked_directory_is_rejected(self):
        (self.root/'assets').mkdir();(self.root/'assets/style.css').write_text('body{}')
        (self.root/'shortcut').symlink_to(self.root/'assets',target_is_directory=True);self.reject('shortcut/style.css')

    def test_link_to_protected_directory_is_rejected(self):
        (self.root/'imports').mkdir();(self.root/'imports/private.html').write_text('SYNTHETIC_MARKER')
        (self.root/'shortcut').symlink_to(self.root/'imports',target_is_directory=True);self.reject('shortcut/private.html')

    def test_entrypoint_search_does_not_issue_session_for_links(self):
        (self.root/'index.html').unlink();(self.root/'.env').write_text('SYNTHETIC_MARKER')
        (self.root/'only.html').symlink_to(self.root/'.env')
        with self.assertRaises(ValueError):self.previews.create('preview','tenant-a')

    def test_standard_entrypoint_does_not_follow_linked_parent(self):
        (self.root/'index.html').unlink();(self.root/'imports').mkdir();(self.root/'imports/index.html').write_text('SYNTHETIC_MARKER')
        (self.root/'app').symlink_to(self.root/'imports',target_is_directory=True)
        with self.assertRaises(ValueError):self.previews.create('preview','tenant-a')

    def test_link_outside_project_is_rejected(self):
        outside=Path(self.tmp.name)/'outside.html';outside.write_text('SYNTHETIC_MARKER')
        (self.root/'outside.html').symlink_to(outside);self.reject('outside.html')


class TestSecurityAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api import cloud_runtime,artifacts
        from app.core.saas import PLATFORM
        from app.core.tenancy import identity_for
        from app.core.security import emitir_token
        cls.client=TestClient(app);cls.runtime=cloud_runtime;cls.artifacts=artifacts;cls.platform=PLATFORM
        from app.api import cloud_projects
        from olympus.cloud.project_studio import ProjectRuntimeManager
        cls.preview_manager=ProjectRuntimeManager(cloud_runtime._RUNTIME.projects)
        cls.preview_patches=[patch.object(module, "_STUDIO_RUNTIMES", cls.preview_manager) for module in [cloud_runtime, cloud_projects]]
        for current in cls.preview_patches:current.start()
        suffix=uuid.uuid4().hex
        cls.owner=identity_for('p0-owner-'+suffix+'@olympus.test');cls.other=identity_for('p0-other-'+suffix+'@olympus.test')
        cls.viewer=identity_for('p0-viewer-'+suffix+'@olympus.test');cls.builder=identity_for('p0-builder-'+suffix+'@olympus.test')
        for identity in [cls.owner,cls.other]:PLATFORM.bootstrap_owner(identity.user_id,identity.email,identity.tenant_id)
        for identity,role in [(cls.viewer,'viewer'),(cls.builder,'builder')]:
            _,token=PLATFORM.invite(cls.owner.tenant_id,cls.owner.user_id,identity.email,role)
            PLATFORM.accept_invitation(token,identity.user_id,identity.email,'SyntheticTestOnlyP0')
        cls.headers={role:{'Authorization':'Bearer '+emitir_token(identity.email,cls.owner.tenant_id if role in {'viewer','builder'} else identity.tenant_id)} for role,identity in [('owner',cls.owner),('other',cls.other),('viewer',cls.viewer),('builder',cls.builder)]}

    def project(self):
        pid='p0-'+uuid.uuid4().hex[:12]
        result=self.client.post('/cloud/projects',headers=self.headers['owner'],json={'project_id':pid,'name':'Synthetic security project'})
        self.assertEqual(result.status_code,201,result.text)
        root=Path(self.runtime._RUNTIME.projects.get(pid).root);(root/'marker.txt').write_text('SYNTHETIC_PRESERVED')
        return pid,root

    def artifact(self,pid,role='owner'):
        return self.client.post('/artifacts',headers=self.headers[role],json={'project_id':pid,'mission_id':'p0','execution_id':'p0','type':'document','name':'synthetic.txt','content_base64':base64.b64encode(b'SYNTHETIC_ARTIFACT').decode(),'metadata':{}})

    def test_other_tenant_delete_has_no_filesystem_or_runtime_effect(self):
        pid,root=self.project();moves=[];stops=[]
        original_move=self.runtime.shutil.move;original_stop=self.runtime._STUDIO_RUNTIMES.stop
        def move(*args,**kw):moves.append(args);return original_move(*args,**kw)
        def stop(*args,**kw):stops.append(args);return original_stop(*args,**kw)
        with patch.object(self.runtime.shutil,'move',side_effect=move),patch.object(self.runtime._STUDIO_RUNTIMES,'stop',side_effect=stop):
            result=self.client.delete('/cloud/projects/'+pid,headers=self.headers['other'])
        self.assertEqual(result.status_code,404)
        self.assertEqual((root/'marker.txt').read_text(),'SYNTHETIC_PRESERVED')
        self.assertEqual(moves,[]);self.assertEqual(stops,[])

    def test_missing_project_does_not_stop_runtime(self):
        stops=[];original=self.runtime._STUDIO_RUNTIMES.stop
        def stop(*args,**kw):stops.append(args);return original(*args,**kw)
        with patch.object(self.runtime._STUDIO_RUNTIMES,'stop',side_effect=stop):
            result=self.client.delete('/cloud/projects/missing-'+uuid.uuid4().hex,headers=self.headers['owner'])
        self.assertEqual(result.status_code,404);self.assertEqual(stops,[])

    def test_authorized_delete_keeps_recoverable_archive(self):
        pid,root=self.project();result=self.client.delete('/cloud/projects/'+pid,headers=self.headers['owner'])
        self.assertEqual(result.status_code,204,result.text);self.assertFalse(root.exists())
        trash=Path(self.runtime._RUNTIME.data_dir)/'project-trash'
        files=list(trash.glob('*'+pid+'/marker.txt'))
        self.assertEqual(len(files),1);self.assertEqual(files[0].read_text(),'SYNTHETIC_PRESERVED')

    def test_viewer_cannot_create_artifact(self):
        pid,_=self.project();before=self.artifacts._STORE.list(self.owner.tenant_id,pid)
        result=self.artifact(pid,'viewer')
        self.assertEqual(result.status_code,403,result.text)
        self.assertEqual(self.artifacts._STORE.list(self.owner.tenant_id,pid),before)

    def test_viewer_cannot_delete_and_can_read_artifact(self):
        pid,_=self.project();created=self.artifact(pid);self.assertEqual(created.status_code,201,created.text)
        aid=created.json()['id'];content=self.artifacts._STORE.content_path(aid,self.owner.tenant_id)
        self.assertEqual(self.client.get('/artifacts/'+aid,headers=self.headers['viewer']).status_code,200)
        self.assertEqual(self.client.get('/artifacts/'+aid+'/download',headers=self.headers['viewer']).content,b'SYNTHETIC_ARTIFACT')
        result=self.client.delete('/artifacts/'+aid,headers=self.headers['viewer'])
        self.assertEqual(result.status_code,403)
        self.assertEqual(content.read_bytes(),b'SYNTHETIC_ARTIFACT')

    def test_builder_can_write_and_other_tenant_cannot_read_or_delete(self):
        pid,_=self.project();created=self.artifact(pid,'builder');self.assertEqual(created.status_code,201,created.text);aid=created.json()['id']
        for path in ['/artifacts/'+aid,'/artifacts/'+aid+'/download']:
            self.assertEqual(self.client.get(path,headers=self.headers['other']).status_code,404)
        self.assertEqual(self.client.delete('/artifacts/'+aid,headers=self.headers['other']).status_code,404)
        self.assertEqual(self.client.delete('/artifacts/'+aid,headers=self.headers['builder']).status_code,204)
        self.assertIsNone(self.artifacts._STORE.get(aid,self.owner.tenant_id))

    def test_http_preview_rejects_link_but_serves_normal_page(self):
        pid,root=self.project();(root/'index.html').write_text('<html><body><main>SECURITY_PREVIEW_OK</main></body></html>')
        (root/'.env').write_text('SYNTHETIC_HIDDEN_MARKER');(root/'linked.html').symlink_to(root/'.env')
        created=self.client.post('/cloud/projects/'+pid+'/preview-session',headers=self.headers['owner'])
        self.assertEqual(created.status_code,201,created.text)
        url=created.json()['preview_url']
        self.assertIn('SECURITY_PREVIEW_OK',self.client.get(url).text)
        rejected=self.client.get(url.rsplit('/',1)[0]+'/linked.html')
        self.assertEqual(rejected.status_code,404)
        self.assertNotIn('SYNTHETIC_HIDDEN_MARKER',rejected.text)

    def test_executable_preview_http_refuses_host_execution(self):
        pid,root=self.project()
        (root/'package.json').write_text(json.dumps({'scripts':{'dev':'next dev'},'dependencies':{'next':'1'}}))
        binary=root/'node_modules/next/dist/bin/next'
        binary.parent.mkdir(parents=True)
        binary.write_text("throw Error('must not execute')")
        with patch('olympus.cloud.project_studio.subprocess.Popen') as popen:
            result=self.client.post('/cloud/projects/'+pid+'/preview-session',headers=self.headers['owner'])
            self.assertEqual(result.status_code,409,result.text)
            self.assertIn('executor isolado',result.json()['detail'])
            self.assertNotIn('preview_url',result.json())
            popen.assert_not_called()
        self.assertEqual((root/'marker.txt').read_text(),'SYNTHETIC_PRESERVED')

    def test_executable_preview_http_hides_other_tenant(self):
        pid,root=self.project()
        (root/'package.json').write_text(json.dumps({'scripts':{'dev':'vite'},'dependencies':{'vite':'1'}}))
        with patch('olympus.cloud.project_studio.subprocess.Popen') as popen:
            result=self.client.post('/cloud/projects/'+pid+'/preview-session',headers=self.headers['other'])
            self.assertEqual(result.status_code,404,result.text)
            self.assertNotIn('executor isolado',result.text)
            popen.assert_not_called()

    def test_health_reports_running_security_build(self):
        result=self.client.get('/health');self.assertEqual(result.status_code,200)
        expected=json.loads((Path(__file__).resolve().parents[1]/'frontend/public/olympus-version.json').read_text())
        self.assertEqual(result.json().get('version'),expected['version'])
        self.assertEqual(result.json().get('build'),expected['build'])

    @classmethod
    def tearDownClass(cls):
        cls.client.close();cls.preview_manager.close()
        for current in reversed(cls.preview_patches):current.stop()
