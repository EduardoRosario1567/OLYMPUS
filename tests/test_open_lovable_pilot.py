"""Offline contract tests for the opt-in Open Lovable pilot adapter."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.integrations.open_lovable import (
    OpenLovableClient, OpenLovableError, OpenLovableWebDeveloper,
    _files_from_generated, _safe_path, _validated_base, _SESSION_LOCK,
)


class FakeRunner:
    def run(self, task, max_iterations, resume):
        return {'original_engine': True}


class FakeClient:
    model = 'llama-3.3-70b-versatile'

    def __init__(self, *, invalid=False, remote_error=False):
        self.calls = []
        self.invalid = invalid
        self.remote_error = remote_error

    def json(self, endpoint, payload):
        self.calls.append(endpoint)
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

    def test_path_traversal_and_no_partial_tags(self):
        for path in ('../secrets.json', 'src/../../secret.ts', '/tmp/x.jsx',
                     'src\\evil.jsx', 'README.md', 'src/sub/../x.jsx',
                     'src/.env', 'src/file.py'):
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
            self.assertEqual(len(client.calls), 3)
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

    def test_pilot_fails_closed(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(
                'os.environ', {'OLYMPUS_OPEN_LOVABLE_EXCLUSIVE': '0'}):
            runner = OpenLovableWebDeveloper(root, FakeRunner(), client=FakeClient())
            self.assertEqual(runner.run('Crie um site').status, 'blocked')

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
