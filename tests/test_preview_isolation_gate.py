"""Qualification control flow only; fixtures are never actual isolation evidence."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts import preview_isolation_gate as gate, release_gate
from tests import test_preview_sessions as fixture
from olympus.cloud.preview_container import PreviewLifecycleError


class GateExecutor(fixture.ControlledContainerExecutor):
    def __init__(self):
        super().__init__()
        self.marker = True
        self.asset_ready = True

    def start(self,*args):
        handle = super().start(*args)
        handle.image_id = 'sha256:'+'a'*64
        return handle

    def fetch(self,handle,target='/',query=''):
        if target != '/':
            return (200 if self.asset_ready else 500),{'Content-Type':'application/javascript'},b'console.log("qualified asset")'
        return 200,{'Content-Type':'text/html'},(gate.MARKER+'<script src="/qualified.js"></script>').encode() if self.marker else b'wrong page'

    def logs(self,handle):
        return [('2026-10-05T00:00:00.000000001Z','stdout',gate.STDOUT_MARKER),
            ('2026-10-05T00:00:00.000000002Z','stderr',gate.STDERR_MARKER)]


class PreviewGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.executor = GateExecutor()
        self.probe = lambda *args:{key:True for key in gate.PROBE_KEYS}

    def qualify(self):
        return gate.qualify(self.executor,self.tmp.name,timeout_seconds=.01,probe=self.probe)

    def test_all_three_frameworks_and_twenty_checks_required(self):
        report = self.qualify()
        self.assertEqual(report['status'],'PASS')
        self.assertEqual([x['framework'] for x in report['frameworks']],list(gate.FRAMEWORKS))
        self.assertTrue(all(len(x['checks'])==20 and all(x['checks'].values()) for x in report['frameworks']))
        self.assertEqual(len(self.executor.stops),3)

    def test_any_failed_isolation_check_stops_matrix_and_cleans_up(self):
        self.probe = lambda *args:dict.fromkeys(gate.PROBE_KEYS,True)|{'network_denied':False}
        report = self.qualify()
        self.assertEqual(report['status'],'FAIL')
        self.assertEqual(len(report['frameworks']),1)
        self.assertEqual(len(self.executor.stops),1)
        self.assertFalse(report['frameworks'][0]['checks']['network_denied'])

    def test_invalid_probe_schema_cannot_approve(self):
        self.probe = lambda *args:{'network_denied':True}
        self.assertEqual(self.qualify()['status'],'FAIL')
        self.assertEqual(len(self.executor.stops),1)

    def test_missing_page_marker_is_not_readiness(self):
        self.executor.marker = False
        report = self.qualify()
        self.assertEqual(report['status'],'FAIL')
        self.assertFalse(report['frameworks'][0]['checks']['framework_http_ready'])

    def test_missing_stderr_emission_cannot_approve(self):
        with patch.object(self.executor,'logs',return_value=[('', 'stdout',gate.STDOUT_MARKER)]):
            report = self.qualify()
        self.assertEqual(report['status'],'FAIL')
        self.assertFalse(report['frameworks'][0]['checks']['stderr_observed'])

    def test_failed_javascript_asset_cannot_approve_html_shell(self):
        self.executor.asset_ready = False
        report = self.qualify()
        self.assertEqual(report['status'],'FAIL')
        self.assertTrue(report['frameworks'][0]['checks']['framework_http_ready'])
        self.assertFalse(report['frameworks'][0]['checks']['javascript_asset_ready'])

    def test_unavailable_docker_is_blocked_without_fallback(self):
        with patch.object(self.executor,'start',side_effect=PreviewLifecycleError('Docker unavailable')):
            report = self.qualify()
        self.assertEqual(report['status'],'BLOCKED')
        self.assertEqual(self.executor.starts,[])
        self.assertEqual(len(report['frameworks']),1)

    def test_unconfirmed_cleanup_blocks_even_when_page_passed(self):
        self.executor.fail_cleanup = True
        report = self.qualify()
        self.assertEqual(report['status'],'BLOCKED')
        self.assertFalse(report['frameworks'][0]['checks']['cleanup_confirmed'])

    def test_probe_transport_failure_cannot_approve_and_still_cleans_up(self):
        def fail(*args):raise RuntimeError('fixture transport error')
        self.probe = fail
        self.assertEqual(self.qualify()['status'],'FAIL')
        self.assertEqual(len(self.executor.stops),1)

    def test_changes_to_host_originals_are_detected(self):
        def mutate(executor,handle,private):
            root = Path(executor.starts[-1][0]);(root/'unchanged.txt').write_text('MUTATED')
            private.write_text('MUTATED')
            return dict.fromkeys(gate.PROBE_KEYS,True)
        self.probe = mutate
        report = self.qualify()
        self.assertEqual(report['status'],'FAIL')
        self.assertFalse(report['frameworks'][0]['checks']['original_project_preserved'])
        self.assertFalse(report['frameworks'][0]['checks']['host_marker_preserved'])

    def test_fixture_dependencies_are_descriptive_without_lock_or_install(self):
        self.qualify()
        for root,framework,_ in self.executor.starts:
            package = json.loads((Path(root)/'package.json').read_text())
            self.assertEqual(package['scripts']['dev'],'never invoked')
            self.assertFalse((Path(root)/'node_modules').exists())

    def test_release_stops_at_preview_block_before_regression(self):
        calls = []
        def run(name,command):
            calls.append((name,command))
            return {'name':name,'status':'PASS' if len(calls)==1 else 'BLOCKED','duration_seconds':0,'output':'fixture'}
        with patch.object(release_gate,'run_gate',side_effect=run),patch.object(release_gate,'REPORT',Path(self.tmp.name)/'release.json'):
            self.assertEqual(release_gate.main(),1)
        self.assertEqual([x[0] for x in calls],['actual-container-isolation','actual-preview-isolation-frameworks'])
        self.assertEqual(calls[1][1][-1],'scripts/preview_isolation_gate.py')
        self.assertEqual(json.loads((Path(self.tmp.name)/'release.json').read_text())['status'],'BLOCKED')
