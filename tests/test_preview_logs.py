"""Logs: actual bounded capture, real manager/API, controlled Docker only."""
from dataclasses import replace
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests import test_preview_container as container_fixture
from tests import test_preview_sessions as session_fixture
from olympus.cloud.preview_container import PreviewLifecycleError
from olympus.agent.container_execution import IsolationUnavailable

STAMP = '2026-10-05T00:00:00.000000001Z'
LATER = '2026-10-05T00:00:00.000000002Z'


class ContainerLogTests(unittest.TestCase):
    setUp = container_fixture.PreviewContainerTests.setUp
    force_cleanup = container_fixture.PreviewContainerTests.force_cleanup
    start = container_fixture.PreviewContainerTests.start

    def test_logging_driver_is_local_with_rotation_limits(self):
        self.start()
        argv = next(args for _,args in self.docker.calls if args[0]=='create')
        for flag in ['--log-driver=local','--log-opt=max-size=1m','--log-opt=max-file=1','--log-opt=compress=false']:
            self.assertIn(flag, argv)

    def test_stdout_stderr_order_and_fixed_bounded_command(self):
        handle = self.start()
        response = subprocess.CompletedProcess([],0,(LATER+' Ready\n').encode(),(STAMP+' Compile error\n').encode())
        with patch.object(self.executor, '_capture_http', return_value=response) as capture:
            entries = self.executor.logs(handle)
        self.assertEqual(entries,[(STAMP,'stderr','Compile error'),(LATER,'stdout','Ready')])
        self.assertEqual(capture.call_args.args[0], [*container_fixture.CLIENT,'logs','--timestamps','--tail=200',handle.name])
        self.assertEqual(capture.call_args.kwargs,dict(timeout_seconds=5,output_limit=262144,stderr_limit=262144,stderr_tail=False))

    def test_stopped_owned_container_logs_are_readable(self):
        handle = self.start()
        self.docker.record['State']['Running'] = False
        with patch.object(self.executor, '_capture_http', return_value=subprocess.CompletedProcess([],0,(STAMP+' Crash\n').encode(),b'')):
            self.assertEqual(self.executor.logs(handle), [(STAMP,'stdout','Crash')])

    def test_untracked_absent_foreign_and_removed_containers_are_rejected(self):
        handle = self.start()
        with patch.object(self.executor, '_capture_http') as capture:
            with self.assertRaises(PreviewLifecycleError):self.executor.logs(replace(handle))
            self.docker.fail = 'foreign_owner'
            with self.assertRaises(PreviewLifecycleError):self.executor.logs(handle)
            capture.assert_not_called()
        self.docker.fail = None
        self.docker.record['Config']['Labels'][container_fixture.PREVIEW_OWNER] = handle.name
        self.executor.stop(handle)
        with self.assertRaises(PreviewLifecycleError):self.executor.logs(handle)

    def test_invalid_logs_fail_without_forwarding_daemon_errors(self):
        handle = self.start()
        responses = [subprocess.CompletedProcess([],1,b'',b'private daemon failure'),
            subprocess.CompletedProcess([],0,b'no timestamp\n',b''),
            subprocess.CompletedProcess([],0,b'2026-99-99T00:00:00.000000001Z invalid\n',b''),
            subprocess.CompletedProcess([],0,((STAMP+' line\n')*201).encode(),b''),
            subprocess.CompletedProcess([],0,b'x'*262145,b'')]
        for response in responses:
            with self.subTest(size=len(response.stdout)),patch.object(self.executor,'_capture_http',return_value=response):
                with self.assertRaises(PreviewLifecycleError):self.executor.logs(handle)

    def test_line_length_is_bounded(self):
        handle = self.start()
        with patch.object(self.executor,'_capture_http',return_value=subprocess.CompletedProcess([],0,(STAMP+' '+'x'*10000+'\n').encode(),b'')):
            self.assertEqual(len(self.executor.logs(handle)[0][2]),4000)

    def test_real_capture_drains_both_streams_and_refuses_overflow(self):
        code = "import sys;sys.stdout.write('out');sys.stderr.write('err')"
        result = self.executor._capture_http([sys.executable,'-c',code],output_limit=4096,stderr_limit=4096,stderr_tail=False)
        self.assertEqual((result.stdout,result.stderr),(b'out',b'err'))
        for stream in ['stdout','stderr']:
            with self.subTest(stream=stream),self.assertRaises(IsolationUnavailable):
                self.executor._capture_http([sys.executable,'-c',"import sys;sys."+stream+".write('x'*100000)"],output_limit=4096,stderr_limit=4096,stderr_tail=False)


class ManagerLogTests(session_fixture.PreviewSessionFixture):
    def test_repeated_polling_keeps_sequences_and_both_streams(self):
        self.manager.start('web','tenant-a')
        self.executor.log_entries = [(STAMP,'stdout','Ready'),(LATER,'stderr','Compile error')]
        first = self.manager.logs('web','tenant-a')
        last = first[-1].seq
        self.assertEqual([(x.stream,x.message) for x in first[-2:]],[('stdout','Ready'),('stderr','Compile error')])
        self.assertEqual(self.manager.logs('web','tenant-a',after=last), [])
        self.executor.log_entries.append((LATER,'stderr','Compile error'))
        self.assertEqual([x.message for x in self.manager.logs('web','tenant-a',after=last)],['Compile error'])

    def test_credentials_and_control_sequences_are_sanitized(self):
        self.manager.start('web','tenant-a')
        self.executor.log_entries = [(STAMP,'stderr','\x1b[31mAPI_KEY=SYNTHETIC_SECRET\x1b[0m'),
            (LATER,'stdout','\x00\x07Ready\r')]
        logs = self.manager.logs('web','tenant-a')
        self.assertEqual([x.message for x in logs[-2:]],['API_KEY=[protegido]','Ready'])

    def test_cross_tenant_request_does_not_read_logs(self):
        self.manager.start('web','tenant-a')
        with self.assertRaises(KeyError):self.manager.logs('web','tenant-b')
        self.assertEqual(self.executor.log_requests, [])

    def test_transient_failure_reports_once_and_recovery_reads_new_output(self):
        self.manager.start('web','tenant-a')
        self.executor.fail_logs = True
        first = self.manager.logs('web','tenant-a')
        self.assertIn('Não foi possível',first[-1].message)
        self.assertEqual(self.manager.logs('web','tenant-a',after=first[-1].seq), [])
        self.executor.fail_logs = False
        self.executor.log_entries = [(STAMP,'stdout','Recovered')]
        self.assertEqual(self.manager.logs('web','tenant-a',after=first[-1].seq)[0].message,'Recovered')

    def test_stopped_and_expired_sessions_do_not_collect_logs(self):
        session = self.manager.start('web','tenant-a')
        session.expires_at = 0
        self.assertEqual(self.manager.logs('web','tenant-a'), [])
        self.assertEqual(self.executor.log_requests, [])
        self.assertNotIn(session.token,self.manager._process_log_cursor)

    def test_retention_and_cleanup_are_bounded(self):
        session = self.manager.start('web','tenant-a')
        for index in range(1100):self.manager._append_log(session.token,'stdout','line '+str(index))
        self.assertEqual(len(self.manager._logs[session.token]),1000)
        self.manager.logs('web','tenant-a')
        self.manager.stop('web','tenant-a')
        self.assertNotIn(session.token,self.manager._process_log_cursor)
        self.assertNotIn(session.token,self.manager._logs)


class APILogTests(session_fixture.PreviewAPIFixture):

    def test_api_returns_sanitized_process_output_and_enforces_tenant(self):
        self.assertEqual(self.client.post('/cloud/projects/web/preview-session').status_code,201)
        self.executor.log_entries = [(STAMP,'stderr','password=SYNTHETIC_SECRET')]
        result = self.client.get('/cloud/projects/web/runtime/logs')
        self.assertEqual(result.status_code,200)
        last = result.json()['logs'][-1]
        self.assertEqual((last['stream'],last['message']),('stderr','password=[protegido]'))
        self.assertEqual(self.client.get('/cloud/projects/web/runtime/logs?after='+str(last['seq'])).json(),{'logs':[]})
        self.identity.tenant_id = 'tenant-b'
        calls = len(self.executor.log_requests)
        self.assertEqual(self.client.get('/cloud/projects/web/runtime/logs').status_code,404)
        self.assertEqual(len(self.executor.log_requests),calls)
