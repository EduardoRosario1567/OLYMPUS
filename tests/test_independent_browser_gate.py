"""Evidence binding and fail-closed regression tests for the static-page gate."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import patch
from olympus.integrations.browser_verifier import BrowserVerifier, artifact_command, validate_receipt, validate_result
from olympus.integrations.open_lovable import OpenLovableWebDeveloper
from tests.test_open_lovable_pilot import FakeClient, FakeRunner


def result(source_sha):
    html='<!doctype html><html lang="pt-BR"><head><title>Rosales</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;background:#f5eee2;color:#2d2018;font:18px Georgia}main{max-width:1000px;margin:auto;padding:40px}h1{font-size:48px}p{line-height:1.6}@media(max-width:600px){main{padding:20px}h1{font-size:32px}}</style></head><body><main><h1>Rosales Café</h1><p>Café com origem e cuidado em cada etapa do nosso trabalho, do grão à xícara.</p><section><h2>Uma proposta entre duas culturas do café</h2><p>Esta apresentação conceitual convida a conhecer a marca e a inspiração que orienta seu desenvolvimento, com atenção aos detalhes e respeito pelo tempo de cada momento.</p></section></main></body></html>'
    return dict(schema='olympus.browser.v1',passed=True,nonce='a'*32,
                source_manifest_sha256=source_sha,artifact_sha256='b'*64,html=html,
                html_sha256=hashlib.sha256(html.encode()).hexdigest(),repairs=[],
                viewports=[dict(viewport=v,passed=True,errors=[]) for v in
                           [dict(width=1440,height=900),dict(width=390,height=844)]])


class GateTests(unittest.TestCase):
    def test_only_private_verifier_origins(self):
        for url in ['https://external.com','http://evil.com','http://localhost/verify','http://user@localhost','http://localhost?x=1']:
            with self.assertRaises(ValueError): BrowserVerifier(url,'a'*32)
        BrowserVerifier('http://verifier.railway.internal:8080','a'*32)

    def test_requires_both_exact_viewports_and_html_checksum(self):
        good=result('a'*64);validate_result(good)
        for change in [dict(passed=False),dict(viewports=[]),dict(html='changed'),dict(schema='other')]:
            with self.assertRaises(ValueError): validate_result(dict(good,**change))

    def test_compiled_reader_is_three_tokens_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            dist=Path(root)/'dist';dist.mkdir();(dist/'index.html').write_text('hello')
            command=artifact_command();self.assertEqual(len(command.split(' ')),3)
            proc=subprocess.run(command.split(' '),cwd=root,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn('OLYMPUS_DIST:',proc.stdout)
            (dist/'link.html').symlink_to(dist/'index.html')
            proc=subprocess.run(command.split(' '),cwd=root,capture_output=True,text=True)
            self.assertNotEqual(proc.returncode,0)

    @patch.dict(os.environ,{'OLYMPUS_ENV':'pilot','OLYMPUS_OPEN_LOVABLE_EXCLUSIVE':'1'})
    def test_adapter_receipt_binds_published_html_and_source(self):
        class CompiledClient(FakeClient):
            def json(self,endpoint,payload=None,**kwargs):
                if payload and payload.get('command')==artifact_command():
                    return dict(success=True,exitCode=0,output='OLYMPUS_DIST:[]\nReturn code: 0\n')
                return super().json(endpoint,payload,**kwargs)
        class Verifier:
            def verify(self,files,source_sha):return result(source_sha)
        with tempfile.TemporaryDirectory() as root:
            runner=OpenLovableWebDeveloper(root,FakeRunner(),client=CompiledClient(),browser_verifier=Verifier())
            report=runner.run('Crie um site web Rosales Café')
            self.assertTrue(report.success,report.error)
            self.assertEqual(report.tests_run,())
            self.assertEqual(report.files_modified[0],'index.html')
            self.assertTrue(validate_receipt(Path(root),report.delivery_review))
            page=Path(root)/'index.html';original=page.read_text();page.write_text('tampered')
            self.assertFalse(validate_receipt(Path(root),report.delivery_review))
            page.write_text(original)
            source=Path(root)/'source/src/App.jsx';source.write_text('tampered')
            self.assertFalse(validate_receipt(Path(root),report.delivery_review))

    @patch.dict(os.environ,{'OLYMPUS_ENV':'pilot','OLYMPUS_OPEN_LOVABLE_EXCLUSIVE':'1'})
    def test_runtime_publishes_only_receipt_bound_static_html(self):
        from olympus.cloud.runtime import CloudRuntime
        class CompiledClient(FakeClient):
            def json(self,endpoint,payload=None,**kwargs):
                if payload and payload.get('command')==artifact_command():
                    return dict(success=True,exitCode=0,output='OLYMPUS_DIST:[]\nReturn code: 0\n')
                return super().json(endpoint,payload,**kwargs)
        class Verifier:
            def verify(self,files,source_sha):return result(source_sha)
        with tempfile.TemporaryDirectory() as root:
            runtime=CloudRuntime(root, lambda workspace,telemetry: OpenLovableWebDeveloper(
                workspace,FakeRunner(),telemetry,client=CompiledClient(),browser_verifier=Verifier()),max_workers=1)
            try:
                rec=runtime.submit('rosales','Crie um site web responsivo da marca Rosales Café com título e apresentação da proposta.')
                deadline=time.time()+5
                while time.time()<deadline and runtime.get(rec.execution_id).status not in ('completed','failed','blocked'):
                    time.sleep(.02)
                current=runtime.get(rec.execution_id)
                events=runtime.events(rec.execution_id)
                self.assertEqual(current.status,'completed',str(events))
                published=next(e for e in events if e['event']=='result_published')
                self.assertTrue(published['version_id'])
            finally:runtime.close()

    def test_forged_browser_status_without_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(validate_receipt(Path(root),dict(browser='passed_independent')))

    def test_real_browser_fixture(self):
        repo=Path(__file__).resolve().parents[1]
        if not (repo/'frontend/node_modules/playwright').exists():
            if os.getenv('CI'):self.fail('CI must install the existing Playwright dependency')
            self.skipTest('Playwright is installed by CI, unavailable locally')
        proc=subprocess.run(['node',str(repo/'tests/independent_browser_gate.cjs')],cwd=repo,
                            capture_output=True,text=True,timeout=100)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
