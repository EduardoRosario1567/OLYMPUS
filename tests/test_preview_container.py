import json
from dataclasses import replace
import base64
import sys
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from olympus.cloud.preview_container import (PreviewContainerExecutor, PreviewLifecycleError,
    PREVIEW_ROLE, PREVIEW_OWNER, PREVIEW_IMAGE)
from olympus.agent.container_execution import ContainerExecutor

IMAGE = "sha256:" + "a" * 64
CLIENT = ("/usr/bin/docker", "--host", "unix:///var/run/docker.sock")


class DockerFixture:
    def __init__(self):
        self.calls = []
        self.record = None
        self.fail = None
        self.invalid_role = False

    def __call__(self, client, *args):
        self.calls.append((client, args))
        if args[:2] == ("image", "inspect"):
            labels = {PREVIEW_ROLE: "wrong" if self.invalid_role else "v1"}
            return subprocess.CompletedProcess(args, 0, json.dumps([{"Id": IMAGE, "Config": {"Labels": labels}}]), "")
        if args[0] == "create":
            name = args[args.index("--name") + 1]
            self.record = {"Name": "/" + name, "Image": IMAGE, "Config": {"Labels": {PREVIEW_ROLE: "v1", PREVIEW_OWNER: name}}, "State": {"Running": False}}
            if self.fail == "create_timeout":
                raise subprocess.TimeoutExpired(args, 10)
            if self.fail == "create_interrupt":
                raise KeyboardInterrupt()
            if self.fail == "create_failure":
                return subprocess.CompletedProcess(args, 125, "", "fixture creation failure")
            return subprocess.CompletedProcess(args, 0, "b" * 64 + "\n", "")
        if args[:2] == ("container", "inspect"):
            if self.record is None:
                return subprocess.CompletedProcess(args, 1, "", "Error: No such container: " + args[2])
            if self.fail == "foreign_owner":
                self.record["Config"]["Labels"][PREVIEW_OWNER] = "foreign"
            return subprocess.CompletedProcess(args, 0, json.dumps([self.record]), "")
        if args[0] == "start":
            if self.fail == "start_failure":
                return subprocess.CompletedProcess(args, 1, "", "fixture start failure")
            if self.fail == "start_timeout":
                raise subprocess.TimeoutExpired(args, 10)
            self.record["State"]["Running"] = self.fail != "stopped"
            return subprocess.CompletedProcess(args, 0, args[1], "")
        if args[0] == "rm":
            if self.fail == "remove_timeout":
                raise subprocess.TimeoutExpired(args, 10)
            if self.fail == "remove_failure":
                return subprocess.CompletedProcess(args, 1, "", "fixture daemon failure")
            if self.fail != "remove_inconclusive":
                self.record = None
            return subprocess.CompletedProcess(args, 0, args[-1], "")
        raise AssertionError(args)


class PreviewContainerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/"project"
        self.root.mkdir()
        (self.root/"package.json").write_text('{}')
        self.executor = PreviewContainerExecutor(journal_root=Path(self.tmp.name)/'journal')
        self.docker = DockerFixture()
        self.client_patch = patch.object(ContainerExecutor, '_client', return_value=CLIENT)
        self.call_patch = patch.object(self.executor, '_call', side_effect=self.docker)
        self.client_patch.start(); self.call_patch.start()
        self.addCleanup(self.client_patch.stop); self.addCleanup(self.call_patch.stop)
        self.addCleanup(self.force_cleanup)

    def force_cleanup(self):
        self.docker.fail = None
        if self.docker.record:
            self.docker.record['Config']['Labels'][PREVIEW_OWNER] = self.docker.record['Name'][1:]
        for handle in tuple(self.executor._pending.values()):
            self.executor.stop(handle)
        self.executor.close()

    def start(self, framework='Next.js', package_path='.'):
        return self.executor.start(self.root, framework, package_path)

    def test_launch_restricts_mounts_network_and_privileges(self):
        handle = self.start()
        argv = next(args for _,args in self.docker.calls if args[0]=='create')
        for flag in ['--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--pull=never','--user=65534:65534','--memory=512m','--pids-limit=128','--cpus=1']:
            self.assertIn(flag,argv)
        self.assertFalse(any(a.startswith(('-p','--publish','--privileged')) for a in argv if a != '--pull=never' and a != '--pids-limit=128'))
        mount = argv[argv.index('--mount')+1]
        self.assertNotIn(str(self.root),mount)
        self.assertTrue(mount.endswith('dst=/snapshot,readonly'))
        self.assertIn(IMAGE,argv)
        self.assertNotIn(PREVIEW_IMAGE,argv)
        self.assertEqual(argv[-2:],('next','.'))
        self.assertEqual(handle.status,'container_running')
        self.assertEqual(self.executor.pending(),())
        self.assertTrue(self.executor.stop(handle))
        self.assertFalse(Path(handle.temporary.name).exists())

    def test_snapshot_excludes_credentials_and_project_dependencies(self):
        (self.root/'.env').write_text('SYNTHETIC_SECRET')
        (self.root/'node_modules').mkdir()
        (self.root/'node_modules/evil.js').write_text('must not load')
        handle=self.start()
        snapshot=Path(handle.temporary.name)/'project'
        self.assertFalse((snapshot/'.env').exists())
        self.assertFalse((snapshot/'node_modules').exists())
        self.assertTrue((snapshot/'package.json').exists())
        self.assertEqual((self.root/'.env').read_text(),'SYNTHETIC_SECRET')

    def test_framework_arguments_are_fixed(self):
        for framework,argument in [('Next.js','next'),('Vite','vite'),('React','react')]:
            with self.subTest(framework=framework):
                handle=self.start(framework)
                argv=next(args for _,args in reversed(self.docker.calls) if args[0]=='create')
                self.assertEqual(argv[-2:],(argument,'.'))
                self.assertTrue(self.executor.stop(handle))

    def test_invalid_package_paths_rejected_before_docker(self):
        for path in ['../other','/tmp','a/../b','.env','a\\b','a\x00b','a//b','a/','',None]:
            with self.subTest(path=path), self.assertRaises(PreviewLifecycleError):
                self.start(package_path=path)
        self.assertEqual(self.docker.calls,[])

    def test_arbitrary_framework_rejected(self):
        with self.assertRaises(PreviewLifecycleError):self.start('node --eval payload')
        self.assertEqual(self.docker.calls,[])

    def test_missing_package_does_not_create_container(self):
        with self.assertRaises(PreviewLifecycleError) as caught:self.start(package_path='missing')
        self.assertTrue(caught.exception.handle.cleanup_confirmed)
        self.assertFalse(any(args[0]=='create' for _,args in self.docker.calls))

    def test_wrong_image_role_rejected(self):
        self.docker.invalid_role=True
        with self.assertRaises(PreviewLifecycleError):self.start()
        self.assertFalse(any(args[0]=='create' for _,args in self.docker.calls))

    def test_image_inspection_timeout_never_creates_container(self):
        with patch.object(self.executor,'_call',side_effect=subprocess.TimeoutExpired(['docker'],10)):
            with self.assertRaises(PreviewLifecycleError):self.start()
        self.assertEqual(self.docker.calls,[])

    def test_startup_failures_remove_owned_container(self):
        for failure in ['create_timeout','create_failure','start_timeout','start_failure','stopped']:
            with self.subTest(failure=failure):
                self.docker.fail=failure
                with self.assertRaises(PreviewLifecycleError) as caught:self.start()
                self.assertTrue(caught.exception.handle.cleanup_confirmed)
                self.assertFalse(Path(caught.exception.handle.temporary.name).exists())
                self.assertIsNone(self.docker.record)

    def test_foreign_identity_is_not_removed_and_cleanup_is_reported(self):
        self.docker.fail='foreign_owner'
        with self.assertRaisesRegex(PreviewLifecycleError,'cleanup_unconfirmed') as caught:self.start()
        handle=caught.exception.handle
        self.assertFalse(handle.cleanup_confirmed)
        self.assertTrue(Path(handle.temporary.name).exists())
        self.assertEqual(self.executor.pending(),(handle,))
        self.assertFalse(any(args[0]=='rm' for _,args in self.docker.calls))

    def test_interrupted_creation_still_removes_owned_container(self):
        self.docker.fail='create_interrupt'
        with self.assertRaises(KeyboardInterrupt):self.start()
        self.assertIsNone(self.docker.record)
        self.assertEqual(self.executor.pending(),())

    def test_other_container_absence_does_not_confirm_removal(self):
        handle=self.start()
        foreign=subprocess.CompletedProcess([],1,'','Error: No such container: another-container')
        with patch.object(self.executor,'_call',return_value=foreign):
            self.assertFalse(self.executor.stop(handle))
        self.assertFalse(handle.cleanup_confirmed)
        self.assertTrue(Path(handle.temporary.name).exists())

    def test_failed_removal_retains_snapshot_for_retry(self):
        for failure in ['remove_timeout','remove_failure','remove_inconclusive']:
            with self.subTest(failure=failure):
                handle=self.start()
                self.docker.fail=failure
                self.assertFalse(self.executor.stop(handle))
                self.assertTrue(Path(handle.temporary.name).exists())
                self.assertEqual(handle.status,'cleanup_unconfirmed')
                self.docker.fail=None
                self.assertTrue(self.executor.stop(handle))
                self.assertFalse(Path(handle.temporary.name).exists())
                self.assertEqual(self.executor.pending(),())

    def test_already_removed_container_is_idempotent(self):
        handle=self.start()
        self.docker.record=None
        self.assertTrue(self.executor.stop(handle))
        calls=len(self.docker.calls)
        self.assertTrue(self.executor.stop(handle))
        self.assertEqual(len(self.docker.calls),calls)

    def test_untracked_handle_cannot_remove_container(self):
        handle=self.start()
        impostor=replace(handle)
        calls=len(self.docker.calls)
        self.assertFalse(self.executor.stop(impostor))
        self.assertEqual(len(self.docker.calls),calls)
        self.assertIsNotNone(self.docker.record)
        self.assertTrue(self.executor.stop(handle))

    def test_linked_root_rejected_before_docker(self):
        link=Path(self.tmp.name)/'linked'
        link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(PreviewLifecycleError):self.executor.start(link,'Next.js')
        self.assertEqual(self.docker.calls,[])

    def test_linked_source_refused_before_creation(self):
        (self.root/'linked.js').symlink_to(self.root/'package.json')
        with self.assertRaises(PreviewLifecycleError):self.start()
        self.assertFalse(any(args[0]=='create' for _,args in self.docker.calls))

    def test_client_environment_has_no_provider_credentials(self):
        with patch('olympus.cloud.preview_container.subprocess.run',return_value=subprocess.CompletedProcess([],0,'','')) as run:
            PreviewContainerExecutor._call(CLIENT,'version')
        self.assertEqual(run.call_args.kwargs['env'],{'PATH': __import__('os').defpath,'HOME':'/nonexistent','LANG':'C.UTF-8'})
        self.assertFalse(run.call_args.kwargs['shell'])

    def test_http_fetch_returns_binary_and_uses_only_container_program(self):
        handle=self.start()
        payload={'status':200,'content_type':'image/png','location':None,'body':base64.b64encode(b'\x00\xffimage').decode()}
        with patch.object(self.executor,'_capture_http',return_value=subprocess.CompletedProcess([],0,json.dumps(payload).encode(),b'')) as capture:
            status,headers,body=self.executor.fetch(handle,'/logo.png','v=1')
        self.assertEqual((status,body),(200,b'\x00\xffimage'))
        self.assertEqual(headers['Content-Type'],'image/png')
        self.assertNotIn('Location',headers)
        argv=capture.call_args.args[0]
        self.assertEqual(argv[:3],list(CLIENT))
        self.assertEqual(argv[3:],['exec','--user=65534:65534',handle.name,'/usr/local/bin/node','/opt/olympus-preview/fetch.mjs','/logo.png','v=1'])

    def test_invalid_http_paths_do_not_contact_docker(self):
        handle=self.start()
        for target in ['http://evil','//evil','/../secret','/%2e%2e/secret','/%252e%252e/secret','/a\\b','/x%00','/x\n','/x?query','/x%zz']:
            with self.subTest(target=target),patch.object(self.executor,'_capture_http') as capture:
                calls=len(self.docker.calls)
                with self.assertRaises(PreviewLifecycleError):self.executor.fetch(handle,target)
                self.assertEqual(len(self.docker.calls),calls)
                capture.assert_not_called()

    def test_http_rejects_untracked_stopped_and_foreign_container(self):
        handle=self.start()
        with patch.object(self.executor,'_capture_http') as capture:
            with self.assertRaises(PreviewLifecycleError):self.executor.fetch(replace(handle))
            self.docker.record['State']['Running']=False
            with self.assertRaises(PreviewLifecycleError):self.executor.fetch(handle)
            self.docker.record['State']['Running']=True
            self.docker.fail='foreign_owner'
            with self.assertRaises(PreviewLifecycleError):self.executor.fetch(handle)
            capture.assert_not_called()

    def test_http_rejects_invalid_response_envelopes(self):
        handle=self.start()
        good={'status':200,'content_type':'text/html','location':None,'body':'b2s='}
        values=[[],{},dict(good,status=True),dict(good,status=999),dict(good,body='%%%'),
            dict(good,content_type='text/html\r\nSet-Cookie: bad'),dict(good,location='/x\nInjected: bad')]
        for value in values:
            with self.subTest(value=value),patch.object(self.executor,'_capture_http',return_value=subprocess.CompletedProcess([],0,json.dumps(value).encode(),b'')):
                with self.assertRaises(PreviewLifecycleError):self.executor.fetch(handle)

    def test_http_response_size_limit(self):
        handle=self.start()
        payload={'status':200,'content_type':'text/html','body':base64.b64encode(b'12345').decode()}
        with patch('olympus.cloud.preview_container.MAX_HTTP_BODY',4),patch.object(self.executor,'_capture_http',return_value=subprocess.CompletedProcess([],0,json.dumps(payload).encode(),b'')):
            with self.assertRaises(PreviewLifecycleError):self.executor.fetch(handle)

    def test_http_timeout_has_no_host_fallback(self):
        handle=self.start()
        with patch.object(self.executor,'_capture_http',side_effect=subprocess.TimeoutExpired(['docker'],10)) as capture:
            with self.assertRaises(PreviewLifecycleError):self.executor.fetch(handle)
            self.assertEqual(capture.call_count,1)
        self.assertEqual(handle.status,'container_running')

    def test_real_transport_drains_and_limits_output(self):
        # Reviewed synthetic programs exercise the actual client capture path.
        result=self.executor._capture_http([sys.executable,'-c',"import sys;sys.stderr.write('x'*50000);sys.stdout.write('{}')"])
        self.assertEqual(result.stdout,b'{}')
        self.assertEqual(len(result.stderr),16000)
        with patch('olympus.cloud.preview_container.MAX_HTTP_ENVELOPE',4096):
            with self.assertRaisesRegex(ValueError,'transport'):
                self.executor._capture_http([sys.executable,'-c',"import sys;sys.stdout.write('x'*100000)"])

    def test_real_transport_timeout_terminates_client(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.executor._capture_http([sys.executable,'-c',"import time;time.sleep(5)"],timeout_seconds=0.05)

    def test_python_node_http_protocol_with_live_fixture(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                seen.append((handler.path,handler.headers.get('Authorization'),handler.headers.get('Cookie')))
                handler.send_response(206);handler.send_header('Content-Type','image/png');handler.end_headers()
                handler.wfile.write(b'\x00\xffLIVE_BRIDGE')
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            handle=self.start()
            uri=(Path(__file__).resolve().parents[1]/'containers/preview-fetch.mjs').as_uri()
            program='import {fetchPreview} from '+json.dumps(uri)+';process.stdout.write(JSON.stringify(await fetchPreview("/logo.png","v=1",{port:'+str(server.server_port)+'})));'
            capture=self.executor._capture_http
            # Replace only Docker exec with the reviewed helper in Node; the
            # production capture, envelope validation and live HTTP are real.
            with patch.object(self.executor,'_capture_http',side_effect=lambda argv:capture([node,'--input-type=module','-e',program])):
                status,headers,body=self.executor.fetch(handle,'/logo.png','v=1')
            self.assertEqual(status,206)
            self.assertEqual(body,b'\x00\xffLIVE_BRIDGE')
            self.assertEqual(headers,{'Content-Type':'image/png'})
            self.assertEqual(seen,[('/logo.png?v=1',None,None)])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
