"""Real filesystem transactions; OS/process/package operations are controlled."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.build_update_bundle import build
from scripts.verify_update_bundle import verify as verify_zip
from scripts.update_macos import (apply_update, UpdateError, MANIFEST, IDENTITY,
                                  GENERATED, MacRuntime, discover_target, read_payload)


class FixtureRuntime:
    def __init__(self, fail=None, callback=None):
        self.fail=fail;self.callback=callback;self.events=[];self.failed=False

    def event(self,name,root):
        self.events.append(name)
        if self.callback:self.callback(name,root)
        if name==self.fail and not self.failed:
            self.failed=True
            raise UpdateError('SYNTHETIC_FAILURE')

    def preflight(self,source,target):self.event('preflight',target)
    def provision(self,source,target):self.event('provision',target)
    def stop(self,target):self.event('stop',target)
    def install_dependencies(self,target):
        for name in GENERATED:
            path=target/name;path.mkdir(parents=True,exist_ok=True);(path/'new-marker').write_text('NEW_DEPENDENCY')
        self.event('install',target)
    def start(self,target):self.event('start',target)
    def confirm(self,target,expected):
        self.event('confirm',target)
        observed=json.loads((target/IDENTITY).read_text())
        if (observed['version'],observed['build'])!=(expected['version'],expected['build']):
            raise UpdateError('SYNTHETIC_VERSION_MISMATCH')


class MacUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve();self.source=self.root/'source';self.target=self.root/'existing'
        self.source.mkdir();self.target.mkdir()
        self.payload={'start_olympus.command':'#!/bin/bash\necho NEW_START\n',
                      IDENTITY:json.dumps({'product':'olympus','version':'3.0.9','build':'DELIVERY-QUALITY-RC2'}),
                      'olympus/example.py':'NEW_CODE\n','new-module.py':'NEW_MODULE\n'}
        for name,data in self.payload.items():
            p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
        self.source_manifest={'format':1,'product':'OLYMPUS','version':'3.0.9','build':'DELIVERY-QUALITY-RC2',
                             'commit':'a'*40,'files':{name:{'sha256':hashlib.sha256(value.encode()).hexdigest(),'mode':0o644} for name,value in self.payload.items()}}
        self.write_manifest()
        for name,data in {'start_olympus.command':'OLD_START\n','olympus/example.py':'OLD_CODE\n',
                          IDENTITY:json.dumps({'product':'olympus','version':'3.0.8','build':'OLD_BUILD'}),
                          'backend/.env':'SYNTHETIC_EXISTING_SECRET=preserved\n',
                          'backend/olympus.db':'SYNTHETIC_EXISTING_DATABASE',
                          '.olympus/cloud/history.json':'SYNTHETIC_HISTORY',
                          'projects/rosales/index.html':'SYNTHETIC_EXISTING_PROJECT',
                          'untracked-local-file.txt':'SYNTHETIC_LOCAL_CUSTOMIZATION'}.items():
            p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
        (self.target/'backend/.env').chmod(0o600)
        self.old_code={name:(self.target/name).read_bytes() for name in self.payload if (self.target/name).is_file()}
        self.protected={name:(self.target/name).read_bytes() for name in ('backend/.env','backend/olympus.db','.olympus/cloud/history.json','projects/rosales/index.html','untracked-local-file.txt')}
        for name in GENERATED:
            p=self.target/name;p.mkdir(parents=True);(p/'old-marker').write_text('OLD_DEPENDENCY')

    def write_manifest(self):
        (self.source/MANIFEST).write_text(json.dumps(self.source_manifest))

    def assert_preserved(self):
        for name,data in self.protected.items():self.assertEqual((self.target/name).read_bytes(),data,name)
        self.assertEqual((self.target/'backend/.env').stat().st_mode&0o777,0o600)

    def assert_restored(self):
        for name,data in self.old_code.items():self.assertEqual((self.target/name).read_bytes(),data,name)
        self.assertFalse((self.target/'new-module.py').exists())
        for name in GENERATED:self.assertEqual((self.target/name/'old-marker').read_text(),'OLD_DEPENDENCY')
        self.assert_preserved()

    def test_success_preserves_all_existing_state_and_retains_backup(self):
        runtime=FixtureRuntime();result=apply_update(self.source,self.target,runtime)
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['target'],str(self.target))
        self.assertEqual(runtime.events,['preflight','provision','stop','install','start','confirm'])
        self.assert_preserved();backup=Path(result['backup'])
        self.assertEqual((backup/'code/olympus/example.py').read_text(),'OLD_CODE\n')
        for name in GENERATED:self.assertEqual((backup/'dependencies'/name/'old-marker').read_text(),'OLD_DEPENDENCY')
        self.assertEqual(len(list(self.root.iterdir())),2)

    def test_failed_stages_restore_code_and_dependencies(self):
        for stage in ('install','start','confirm'):
            with self.subTest(stage=stage):
                # Each subcase has its own complete filesystem fixture.
                other=MacUpdateTests('test_success_preserves_all_existing_state_and_retains_backup');other.setUp()
                try:
                    with self.assertRaisesRegex(UpdateError,'restaurados'):
                        apply_update(other.source,other.target,FixtureRuntime(fail=stage))
                    other.assert_restored()
                finally:other.doCleanups()

    def test_preflight_and_provision_failure_do_not_modify_code_or_dependencies(self):
        for stage in ('preflight','provision'):
            with self.subTest(stage=stage), self.assertRaises(UpdateError):
                apply_update(self.source,self.target,FixtureRuntime(fail=stage))
            self.assert_restored()

    def test_tampered_payload_is_rejected_before_runtime_calls(self):
        (self.source/'olympus/example.py').write_text('TAMPERED')
        runtime=FixtureRuntime()
        with self.assertRaisesRegex(UpdateError,'Integridade'):apply_update(self.source,self.target,runtime)
        self.assertEqual(runtime.events,[]);self.assert_restored()

    def test_protected_paths_and_case_collision_are_rejected(self):
        names=('backend/.env','.olympus/cloud/history.json','projects/rosales/index.html',
               '../outside.py','backend/secret.key','a//b.py','olympus/../escape.py')
        for name in names:
            with self.subTest(name=name):
                changed=copy.deepcopy(self.source_manifest);changed['files'][name]={'sha256':'a'*64,'mode':0o644}
                (self.source/MANIFEST).write_text(json.dumps(changed))
                with self.assertRaises(UpdateError):read_payload(self.source)
        changed=copy.deepcopy(self.source_manifest);changed['files']['OLYMPUS/example.py']=changed['files']['olympus/example.py']
        (self.source/'OLYMPUS').mkdir(exist_ok=True);(self.source/'OLYMPUS/example.py').write_text(self.payload['olympus/example.py'])
        (self.source/MANIFEST).write_text(json.dumps(changed))
        with self.assertRaisesRegex(UpdateError,'colidem'):read_payload(self.source)
        self.assert_restored()

    def test_linked_code_destination_cannot_write_external_file(self):
        (self.target/'olympus/example.py').unlink()
        external=self.root/'outside';external.write_text('OUTSIDE_PRESERVED')
        (self.target/'olympus/example.py').symlink_to(external)
        with self.assertRaisesRegex(UpdateError,'Link'):apply_update(self.source,self.target,FixtureRuntime())
        self.assertEqual(external.read_text(),'OUTSIDE_PRESERVED');self.assert_preserved()

    def test_partial_dependency_move_restores_only_moved_directories(self):
        original=Path.rename
        def fail_second(path,destination):
            if path==self.target/'frontend/node_modules':raise OSError('SYNTHETIC_MOVE_FAILURE')
            return original(path,destination)
        with patch.object(Path,'rename',fail_second),self.assertRaises(UpdateError):
            apply_update(self.source,self.target,FixtureRuntime())
        self.assert_restored()

    def test_concurrent_code_change_is_preserved_and_backup_retained(self):
        def mutate(event,root):
            if event=='start':(root/'olympus/example.py').write_text('CONCURRENT_CODE\n')
        with self.assertRaisesRegex(UpdateError,'incompleta'):
            apply_update(self.source,self.target,FixtureRuntime(fail='start',callback=mutate))
        self.assertEqual((self.target/'olympus/example.py').read_text(),'CONCURRENT_CODE\n')
        self.assert_preserved();self.assertTrue(list((self.target/'.olympus/backups').glob('UPDATE-*')))

    def test_foreign_port_identity_is_rejected_without_stopping(self):
        runtime=MacRuntime()
        with patch.object(runtime,'listeners',return_value=[(8000,42,self.root/'another-app')]),self.assertRaises(UpdateError):
            runtime.check_owned(self.target)
        self.assert_restored()

    def test_target_discovery_prefers_running_installation(self):
        runtime=MacRuntime()
        with patch.object(runtime,'listeners',return_value=[(8000,42,self.target),(3000,43,self.target/'frontend')]):
            self.assertEqual(discover_target(runtime),self.target)

    def test_real_cli_refuses_non_macos_before_mutation(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/update_macos.py'),
                               '--source',str(self.source),'--target',str(self.target)],capture_output=True,text=True)
        if sys.platform=='darwin':
            self.assertNotEqual(result.returncode,0)  # Fixture has no real runtime/dependencies.
        else:self.assertIn('exclusivo para macOS',result.stderr)
        self.assert_restored()

    def test_package_roundtrip_hashes_and_file_modes(self):
        archive=self.root/'candidate.zip';first=build(self.source,archive,self.payload.keys(),'a'*40)
        self.assertEqual(first['files'],self.source_manifest['files'])
        extracted=self.root/'extracted';extracted.mkdir()
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip());z.extractall(extracted)
        checked,payload=read_payload(extracted/'OLYMPUS-UPDATE')
        self.assertEqual(checked['commit'],'a'*40);self.assertEqual(payload['olympus/example.py'][0],b'NEW_CODE\n')
        before=archive.read_bytes();build(self.source,archive,self.payload.keys(),'a'*40)
        self.assertEqual(before,archive.read_bytes())
        self.assertEqual(verify_zip(archive)['file_count'],len(self.payload))


    def test_interrupted_transaction_blocks_a_second_update(self):
        earlier=self.target/'.olympus/backups/UPDATE-interrupted'
        earlier.mkdir(parents=True);(earlier/'transaction.json').write_text('{"status":"PREPARED"}')
        runtime=FixtureRuntime()
        with self.assertRaisesRegex(UpdateError,'anterior interrompida'):
            apply_update(self.source,self.target,runtime)
        self.assertEqual(runtime.events,[]);self.assert_restored()

    def test_keyboard_interrupt_rolls_back(self):
        def interrupt(event,root):
            if event=='install':raise KeyboardInterrupt()
        with self.assertRaisesRegex(UpdateError,'restaurados'):
            apply_update(self.source,self.target,FixtureRuntime(callback=interrupt))
        self.assert_restored()


    def test_abrupt_process_exit_is_recovered_on_next_update(self):
        import subprocess,sys
        program="""import os,sys
from pathlib import Path
from scripts.update_macos import apply_update
from tests.test_update_macos import FixtureRuntime
def terminate(event,root):
    if event=='install':os._exit(77)
apply_update(Path(sys.argv[1]),Path(sys.argv[2]),FixtureRuntime(callback=terminate))
"""
        result=subprocess.run([sys.executable,'-c',program,str(self.source),str(self.target)],
                              cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,77,result.stderr)
        earlier=next((self.target/'.olympus/backups').glob('UPDATE-*'))
        runtime=FixtureRuntime();result=apply_update(self.source,self.target,runtime)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(json.loads((earlier/'result.json').read_text())['status'],'RECOVERED_AFTER_INTERRUPTION')
        self.assertEqual(runtime.events[:3],['stop','start','confirm']);self.assert_preserved()

    def test_private_backup_contains_existing_credentials_and_history(self):
        result=apply_update(self.source,self.target,FixtureRuntime());backup=Path(result['backup'])
        for name,content in self.protected.items():
            self.assertEqual((backup/'persistent'/name).read_bytes(),content)
        self.assertEqual(backup.stat().st_mode&0o777,0o700)
        self.assertEqual((backup/'persistent/backend/.env').stat().st_mode&0o777,0o600)

    def test_service_stop_failure_during_rollback_keeps_dependencies_in_place(self):
        stop_calls=[0]
        def callback(event,root):
            if event=='stop':
                stop_calls[0]+=1
                if stop_calls[0]==2:raise UpdateError('SYNTHETIC_BUSY_SERVICE')
        with self.assertRaisesRegex(UpdateError,'não pôde ser encerrado'):
            apply_update(self.source,self.target,FixtureRuntime(fail='start',callback=callback))
        for name in GENERATED:self.assertTrue((self.target/name/'new-marker').is_file())
        self.assertEqual((self.target/'olympus/example.py').read_text(),'NEW_CODE\n')
        self.assert_preserved()

    def test_concurrent_persistent_change_is_not_overwritten(self):
        def mutate(event,root):
            if event=='install':(root/'projects/rosales/index.html').write_text('CONCURRENT_USER_CHANGE')
        with self.assertRaisesRegex(UpdateError,'incompleta'):
            apply_update(self.source,self.target,FixtureRuntime(callback=mutate))
        self.assertEqual((self.target/'projects/rosales/index.html').read_text(),'CONCURRENT_USER_CHANGE')
        backup=next((self.target/'.olympus/backups').glob('UPDATE-*'))
        self.assertEqual((backup/'persistent/projects/rosales/index.html').read_bytes(),self.protected['projects/rosales/index.html'])


    def test_zip_rejects_traversal_links_extra_files_and_tampering(self):
        import stat
        original=self.root/'original.zip';build(self.source,original,self.payload.keys(),'a'*40)
        for case in ('traversal','link','extra','tamper','mode'):
            with self.subTest(case=case):
                output=self.root/(case+'.zip')
                with zipfile.ZipFile(original) as source,zipfile.ZipFile(output,'w') as target:
                    for info in source.infolist():
                        data=source.read(info)
                        if info.filename.endswith('/olympus/example.py'):
                            if case=='tamper':data=b'UNTRUSTED_CHANGE'
                            elif case=='mode':info.external_attr=(stat.S_IFREG|0o755)<<16
                        target.writestr(info,data)
                    if case in ('traversal','link','extra'):
                        name={'traversal':'OLYMPUS-UPDATE/../escape','link':'OLYMPUS-UPDATE/linked.py',
                              'extra':'OLYMPUS-UPDATE/unlisted.py'}[case]
                        info=zipfile.ZipInfo(name);info.external_attr=((stat.S_IFLNK if case=='link' else stat.S_IFREG)|0o644)<<16
                        target.writestr(info,b'UNTRUSTED_ENTRY')
                with self.assertRaises(UpdateError):verify_zip(output)

    def test_process_stop_refuses_foreign_owner_before_any_signal(self):
        runtime=MacRuntime()
        with patch.object(runtime,'listeners',return_value=[(8000,42,self.target),(3000,43,self.root/'foreign')]),patch('os.kill') as kill:
            with self.assertRaises(UpdateError):runtime.stop(self.target)
            kill.assert_not_called()


    def test_existing_env_template_is_preserved_including_local_values(self):
        name='backend/.env.example'
        (self.source/'backend').mkdir()
        (self.source/name).write_text('SYNTHETIC_DEFAULT_TEMPLATE')
        (self.target/name).write_text('SYNTHETIC_EXISTING_LOCAL_VALUE')
        self.source_manifest['files'][name]={'sha256':hashlib.sha256((self.source/name).read_bytes()).hexdigest(),'mode':0o644}
        self.write_manifest()
        result=apply_update(self.source,self.target,FixtureRuntime())
        self.assertEqual(result['status'],'PASS')
        self.assertEqual((self.target/name).read_text(),'SYNTHETIC_EXISTING_LOCAL_VALUE')
        self.assert_preserved()

    def test_package_inside_installation_is_rejected(self):
        import shutil
        nested=self.target/'nested-package';shutil.copytree(self.source,nested)
        runtime=FixtureRuntime()
        with self.assertRaisesRegex(UpdateError,'fora da instalação'):
            apply_update(nested,self.target,runtime)
        self.assertEqual(runtime.events,[]);self.assert_restored()

    def test_failed_atomic_write_restores_previous_files_and_modes(self):
        from scripts.update_macos import atomic
        failed=[False]
        (self.target/'start_olympus.command').chmod(0o755)
        def fail_once(path,content,mode=0o644):
            if path==self.target/'olympus/example.py' and not failed[0]:
                failed[0]=True;raise OSError('SYNTHETIC_STORAGE_FAILURE')
            return atomic(path,content,mode)
        with patch('scripts.update_macos.atomic',side_effect=fail_once),self.assertRaisesRegex(UpdateError,'restaurados'):
            apply_update(self.source,self.target,FixtureRuntime())
        self.assert_restored();self.assertEqual((self.target/'start_olympus.command').stat().st_mode&0o777,0o755)

    def test_package_builder_refuses_state_and_links(self):
        with self.assertRaises(UpdateError):build(self.source,self.root/'bad.zip',['backend/.env'],'a'*40)
        (self.source/'link.py').symlink_to(self.source/'olympus/example.py')
        with self.assertRaises(ValueError):build(self.source,self.root/'bad.zip',['link.py'],'a'*40)
