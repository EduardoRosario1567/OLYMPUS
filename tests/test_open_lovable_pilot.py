"""Offline contract tests for the opt-in Open Lovable pilot adapter."""
import hashlib
import json
import tempfile
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.integrations.open_lovable import (
    OpenLovableClient, OpenLovableError, OpenLovableWebDeveloper,
    _files_from_generated, _safe_path, _validated_base, _verify_export, _SESSION_LOCK,
    _pilot_process_lock, pilot_tenant_authorized,
    _command_passed, _entrypoint_restore_command, _verify_presentation_sources,
)


class FakeRunner:
    def run(self, task, max_iterations, resume):
        return {'original_engine': True}


class FakeClient:
    model = 'llama-3.3-70b-versatile'

    def __init__(self, *, invalid=False, remote_error=False, bad_build=False,
                 bad_export=False, missing_export=False, changed_sandbox=False,
                 malicious_export=False):
        self.calls = []
        self.invalid = invalid
        self.remote_error = remote_error
        self.bad_build = bad_build
        self.bad_export = bad_export
        self.missing_export = missing_export
        self.changed_sandbox = changed_sandbox
        self.malicious_export = malicious_export

    def json(self, endpoint, payload=None, *, max_bytes=128 * 1024):
        self.calls.append(endpoint)
        if endpoint.endswith('run-command-v2'):
            return {
                'success': True, 'exitCode': 0,
                'output': 'STDOUT:\nVite build complete\nReturn code: ' + ('1' if self.bad_build else '0') + '\n',
            }
        if endpoint.endswith('sandbox-status'):
            return {'success': True, 'active': True, 'healthy': True,
                    'sandboxData': {'sandboxId': 'other-sandbox' if self.changed_sandbox else 'sandbox-01'}}
        if endpoint.endswith('olympus-export'):
            if self.missing_export:
                raise OpenLovableError('404 upstream endpoint')
            sources = {
                'src/App.jsx': 'export default function App(){ return <h1>Rosales Café</h1> }\n',
                'src/main.jsx': "import App from './App.jsx';\n",
                'index.html': '<!doctype html><html><body><div id="root"></div></body></html>\n',
                'package.json': json.dumps({'name': 'rosales', 'scripts': {'build': 'vite build'}}),
            }
            if self.malicious_export:
                sources['src/../secret.jsx'] = 'secret'
            files = [
                {'path': name, 'content': value,
                 'sha256': hashlib.sha256(value.encode('utf-8')).hexdigest()}
                for name, value in sorted(sources.items())
            ]
            project_hash = hashlib.sha256()
            for entry in files:
                project_hash.update(entry['path'].encode('utf-8') + b'\0')
                project_hash.update(bytes.fromhex(entry['sha256']))
            if self.bad_export:
                files[0]['sha256'] = '0' * 64
            return {'success': True, 'sandboxId': 'sandbox-01',
                    'files': files, 'sha256': project_hash.hexdigest()}
        return {'success': True, 'sandboxId': 'sandbox-01'}

    def sse(self, endpoint, payload):
        self.calls.append(endpoint)
        if endpoint.endswith('generate-ai-code-stream'):
            code = '<file path="src/App.jsx">export default function App(){ return <h1>Rosales Café</h1> }</file>'
            if self.invalid:
                code = '<file path="../bad.jsx">evil</file>'
            return {'type': 'complete', 'generatedCode': code}
        return {'type': 'complete', 'results': {
            'filesCreated': ['src/App.jsx'],
            'errors': ['failed'] if self.remote_error else [],
        }}


class OpenLovableContractTests(unittest.TestCase):
    def test_build_cannot_hide_a_failed_final_return_code(self):
        for output in ('Return code: 0\nSTDERR:\nerror\nReturn code: 1\n',
                       'Return code: 0\nnot the final result', '', 'Return code: 00'):
            self.assertFalse(_command_passed({'success': True, 'exitCode': 0, 'output': output}))
        self.assertTrue(_command_passed({'success': True, 'exitCode': 0,
                                        'output': 'STDOUT:\nbuilt in 1s\nReturn code: 0\n'}))
        self.assertFalse(_command_passed({'success': True, 'exitCode': False,
                                         'output': 'Return code: 0'}))

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_truncated_generation_retries_before_any_application(self):
        class TruncatedOnce(FakeClient):
            def __init__(self):
                super().__init__()
                self.generations = 0

            def sse(self, endpoint, payload):
                if endpoint.endswith('generate-ai-code-stream'):
                    self.generations += 1
                    if self.generations == 1:
                        self.calls.append(endpoint)
                        return {'generatedCode': '<file path="src/App.jsx">incomplete'}
                return super().sse(endpoint, payload)

        with tempfile.TemporaryDirectory() as root:
            client = TruncatedOnce()
            events = []
            result = OpenLovableWebDeveloper(root, FakeRunner(), events.append, client=client).run('Crie um site')
            self.assertTrue(result.success)
            self.assertEqual(client.generations, 2)
            self.assertEqual(result.iterations, 2)
            self.assertEqual(client.calls.count('/api/apply-ai-code-stream'), 1)
            self.assertTrue(any(e['event'] == 'open_lovable_generation_retry' for e in events))

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_repeated_truncation_stops_without_mutating_remote_sources(self):
        class AlwaysTruncated(FakeClient):
            def sse(self, endpoint, payload):
                self.calls.append(endpoint)
                return {'generatedCode': '<file path="src/App.jsx">incomplete'}

        with tempfile.TemporaryDirectory() as root:
            client = AlwaysTruncated()
            result = OpenLovableWebDeveloper(root, FakeRunner(), client=client).run('Crie um site')
            self.assertEqual(result.status, 'blocked')
            self.assertEqual(client.calls.count('/api/generate-ai-code-stream'), 2)
            self.assertNotIn('/api/apply-ai-code-stream', client.calls)
            self.assertFalse((Path(root) / 'src/App.jsx').exists())

    def test_entrypoint_writer_survives_upstream_space_splitting(self):
        # Reproduces E2B command.split(' '), with quotes, accents and spaces
        # carried as data. A shell-like payload must remain literal text.
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'src').mkdir()
            (Path(root) / 'src/main.jsx').write_text('stripped')
            (Path(root) / 'index.html').write_text('default')
            proposed = {Path('src/main.jsx'): "import './index.css';\n// café $(touch NEVER) `literal`\n",
                        Path('index.html'): '<html lang="pt-BR"><title>Rosales Café</title></html>\n'}
            command = _entrypoint_restore_command(proposed)
            self.assertEqual(len(command.split(' ')), 3)
            result = subprocess.run(command.split(' '), cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('OLYMPUS_ENTRYPOINTS_RESTORED', result.stdout)
            for path, content in proposed.items():
                self.assertEqual((Path(root) / path).read_text(), content)
            self.assertFalse((Path(root) / 'NEVER').exists())

    def test_entrypoint_writer_rejects_linked_files(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'src').mkdir()
            outside = Path(root) / 'outside.jsx'
            outside.write_text('untouched')
            (Path(root) / 'src/main.jsx').symlink_to(outside)
            command = _entrypoint_restore_command({Path('src/main.jsx'): 'new'})
            result = subprocess.run(command.split(' '), cwd=root, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(outside.read_text(), 'untouched')

    def test_stylesheet_loss_and_metadata_reset_are_not_accepted(self):
        original = {Path('src/App.jsx'): "import './index.css';\nexport default()=> <h1>Rosales</h1>;",
                    Path('src/index.css'): 'body { color: brown; }'}
        _verify_presentation_sources(original, original)
        broken = dict(original)
        broken[Path('src/App.jsx')] = 'export default()=> <h1>Rosales</h1>;'
        with self.assertRaisesRegex(OpenLovableError, 'Stylesheet import removed'):
            _verify_presentation_sources(broken, original)
        broken = {p: c for p, c in original.items() if p.suffix != '.css'}
        with self.assertRaisesRegex(OpenLovableError, 'stylesheet missing'):
            _verify_presentation_sources(broken, original)
        with self.assertRaisesRegex(OpenLovableError, 'entrypoint changed'):
            _verify_presentation_sources({Path('index.html'): '<title>Sandbox App</title>'},
                                         {Path('index.html'): '<title>Rosales Café</title>'})

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1', 'OLYMPUS_ENV': 'development'})
    def test_cloud_runtime_still_blocks_publication_without_browser_evidence(self):
        from olympus.cloud.runtime import CloudRuntime
        with tempfile.TemporaryDirectory() as root, patch.dict('os.environ', {
                'OLYMPUS_OPEN_LOVABLE_LOCK_DIR': str(Path(root) / 'locks')}):
            runtime = CloudRuntime(str(Path(root) / 'runtime'),
                                   lambda workspace, telemetry: OpenLovableWebDeveloper(
                                       workspace, FakeRunner(), telemetry, client=FakeClient()),
                                   max_workers=1)
            self.addCleanup(runtime.close)
            rec = runtime.submit('rosales-gate', 'Crie um site Rosales Café')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                current = runtime.get(rec.execution_id)
                if current.status in {'completed', 'failed', 'blocked'}:
                    break
                time.sleep(0.01)
            self.assertEqual(current.status, 'blocked', current.error)
            events = runtime.events(rec.execution_id)
            self.assertTrue(any(e['event'] == 'open_lovable_verification_blocked' for e in events))
            self.assertFalse(any(e['event'] == 'result_published' for e in events))
            self.assertTrue((Path(current.workspace) / 'src/App.jsx').exists())

    def test_tenant_allowlist_is_fail_closed(self):
        self.assertFalse(pilot_tenant_authorized(None, None))
        self.assertFalse(pilot_tenant_authorized('tenant-a', None))
        self.assertFalse(pilot_tenant_authorized('tenant-b', 'tenant-a'))
        self.assertTrue(pilot_tenant_authorized('tenant-a', 'tenant-a'))

    def test_url_policy(self):
        self.assertEqual(
            _validated_base('http://open-lovable-upstream.railway.internal:8080'),
            'http://open-lovable-upstream.railway.internal:8080',
        )
        for bad in ('http://evil.example', 'https://example.com',
                    'http://localhost:1234/path', 'https://user:pass@pilot.up.railway.app'):
            with self.subTest(bad=bad), self.assertRaises(OpenLovableError):
                _validated_base(bad)
        with self.assertRaises(OpenLovableError):
            OpenLovableClient('https://pilot.up.railway.app', 'good-model')
        with self.assertRaisesRegex(OpenLovableError, 'export token'):
            OpenLovableClient('http://localhost:8080', 'good-model').json(
                '/api/olympus-export', {'sandboxId': 'sandbox-01'}
            )

    def test_path_traversal_and_no_partial_tags(self):
        for path in ('../secrets.json', 'src/../../secret.ts', '/tmp/x.jsx',
                     'src\\evil.jsx', 'README.md', 'src/sub/../x.jsx',
                     'src/.env', 'src/.env.jsx', 'src/file.py'):
            with self.subTest(path=path), self.assertRaises(OpenLovableError):
                _safe_path(path)
        with self.assertRaises(OpenLovableError):
            _files_from_generated('<file path="src/App.jsx">incomplete')
        with self.assertRaises(OpenLovableError):
            _files_from_generated('<file path="src/styles.css">hello</file>')

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_web_generated_files_and_events(self):
        with tempfile.TemporaryDirectory() as root:
            client = FakeClient()
            events = []
            runner = OpenLovableWebDeveloper(root, FakeRunner(), events.append, client=client)
            result = runner.run('Crie um site para Rosales Café')
            self.assertEqual(result.status, 'completed')
            self.assertIn('Rosales Café', (Path(root) / 'src/App.jsx').read_text())
            self.assertTrue((Path(root) / 'index.html').exists())
            self.assertTrue((Path(root) / 'package.json').exists())
            self.assertEqual(len(client.calls), 7)
            self.assertIn('/api/run-command-v2', client.calls)
            self.assertIn('/api/olympus-export', client.calls)
            self.assertEqual(len(result.delivery_review['export_sha256']), 64)
            self.assertIn('sandbox_react_build', result.tests_run)
            self.assertEqual(events[-1]['event'], 'open_lovable_files_ready')

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_other_tasks_and_remote_failures(self):
        with tempfile.TemporaryDirectory() as root:
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient(invalid=True))
            self.assertEqual(runner.run('Calcule 4 mais 8'), {'original_engine': True})
            self.assertEqual(runner.run('Crie um site profissional').status, 'blocked')
            self.assertFalse((Path(root) / 'src/App.jsx').exists())
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient(remote_error=True))
            self.assertEqual(runner.run('Crie um site profissional').status, 'blocked')
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient(bad_build=True))
            self.assertEqual(runner.run('Crie um site profissional').status, 'blocked')

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_export_contract_rejects_incomplete_or_tampered_snapshots(self):
        with tempfile.TemporaryDirectory() as root:
            for mode in ({'missing_export': True}, {'bad_export': True},
                         {'changed_sandbox': True}, {'malicious_export': True}):
                with self.subTest(mode=mode):
                    client = FakeClient(**mode)
                    runner = OpenLovableWebDeveloper(root, FakeRunner(), client=client)
                    result = runner.run('Crie um site profissional')
                    self.assertEqual(result.status, 'blocked')
                    self.assertFalse((Path(root) / 'src/App.jsx').exists())
                    self.assertFalse((Path(root) / 'index.html').exists())

    def test_export_rejects_missing_entrypoint_and_manifest_drift(self):
        client = FakeClient()
        payload = client.json('/api/olympus-export')
        with self.assertRaises(OpenLovableError):
            _verify_export(payload, 'wrong-sandbox', {'src/App.jsx'})
        payload['files'] = [f for f in payload['files'] if f['path'] != 'index.html']
        with self.assertRaises(OpenLovableError):
            _verify_export(payload, 'sandbox-01', {'src/App.jsx'})

    @patch.dict('os.environ', {
        'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1', 'OLYMPUS_ENV': 'production',
    })
    def test_production_fails_closed_even_when_exclusive(self):
        with tempfile.TemporaryDirectory() as root:
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient())
            result = runner.run('Crie um site profissional')
            self.assertEqual(result.status, 'blocked')
            self.assertIn('production disabled', result.error)

    def test_pilot_fails_closed(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
                'os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '0'}):
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient())
            self.assertEqual(runner.run('Crie um site').status, 'blocked')

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_pilot_does_not_reenter_held_host_lease(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
                'os.environ', {'OLYMPUS_OPEN_LOVABLE_LOCK_DIR': str(Path(root) / 'locks')}):
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient())
            with _pilot_process_lock():
                result = runner.run('Crie um site para Rosales Café')
            self.assertEqual(result.status, 'blocked')
            self.assertIn('local worker', result.error)
            self.assertFalse((Path(root) / 'src/App.jsx').exists())

    @patch.dict('os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '1'})
    def test_simultaneous_missions_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient())
            _SESSION_LOCK.acquire()
            try:
                self.assertEqual(runner.run('Crie um site').status, 'blocked')
            finally:
                _SESSION_LOCK.release()


if __name__ == '__main__':
    unittest.main()
