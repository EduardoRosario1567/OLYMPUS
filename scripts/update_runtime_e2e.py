#!/usr/bin/env python3
"""macOS QA: real venv/npm/processes/HTTP; Docker proof is a separate Linux gate."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.update_macos import MacRuntime, apply_update, IDENTITY, digest
from scripts.verify_update_bundle import verify


class NativeRuntime(MacRuntime):
    def call(self,command,cwd=None,timeout=30):
        result=subprocess.run(command,cwd=cwd,env=self.environment(),stdin=subprocess.DEVNULL,
                              capture_output=True,timeout=timeout,shell=False)
        if result.returncode:
            self.failed_command_output=(result.stdout+result.stderr).decode(errors='replace')[-16000:]
            self.failed_command_name=Path(command[0]).name
            raise RuntimeError('Native QA command failed: '+self.failed_command_name)
        return result.stdout

    def preflight(self,source,target):
        if sys.platform!='darwin':raise RuntimeError('Native macOS qualification required')
        self.check_owned(target)

    def provision(self,source,target):
        # Explicit QA boundary: hosted macOS runner has no Docker Desktop.
        # Production MacRuntime always provisions and proves the local images.
        pass


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--old-source',required=True)
    parser.add_argument('--archive',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args();verified=verify(args.archive);runtime=NativeRuntime()
    with tempfile.TemporaryDirectory(prefix='olympus-native-update-') as directory:
        root=Path(directory).resolve();target=root/'OLYMPUS-EXISTING'
        shutil.copytree(args.old_source,target,ignore=shutil.ignore_patterns('.git','.olympus','.venv','node_modules','.next','__pycache__'))
        with zipfile.ZipFile(args.archive) as archive:archive.extractall(root/'package')
        source=root/'package/OLYMPUS-UPDATE'
        previous=json.loads((target/IDENTITY).read_text());previous['build']='SYNTHETIC-PREVIOUS-QUALIFIED-BUILD'
        (target/IDENTITY).write_text(json.dumps(previous)+'\n')
        env=target/'backend/.env'
        env.write_text('OLYMPUS_ADMIN_EMAIL=qa@olympus.local\nOLYMPUS_ADMIN_SENHA=synthetic-update-only-password\n'
                       'OLYMPUS_JWT_SECRET=synthetic-update-only-0123456789abcdef0123456789abcdef\n')
        env.chmod(0o600)
        project=target/'projects/SYNTHETIC/index.html';project.parent.mkdir(parents=True);project.write_text('SYNTHETIC_PROJECT_PRESERVED')
        history=target/'.olympus/history.txt';history.parent.mkdir(exist_ok=True);history.write_text('SYNTHETIC_HISTORY_PRESERVED')
        protected={str(p.relative_to(target)):digest(p) for p in (env,project,history)}
        try:
            runtime.install_dependencies(target)
            runtime.start(target);runtime.confirm(target,previous)
            old_pids={pid for _,pid,_ in runtime.listeners()}
            result=apply_update(source,target,runtime)
            new_pids={pid for _,pid,_ in runtime.listeners()}
            checks={'update_passed':result['status']=='PASS','fresh_service_pids':not bool(old_pids&new_pids),
                    'same_target':result['target']==str(target),'exact_commit':result['commit']==verified['commit'],
                    'credential_preserved':digest(env)==protected['backend/.env'],
                    'credential_mode_preserved':env.stat().st_mode&0o777==0o600,
                    'project_preserved':digest(project)==protected['projects/SYNTHETIC/index.html'],
                    'history_preserved':digest(history)==protected['.olympus/history.txt'],
                    'backup_retained':Path(result['backup']).is_dir()}
            report={'status':'PASS' if all(checks.values()) else 'FAIL','boundary':'native-macos-processes-dependencies-http',
                    'docker_boundary':'not exercised here; independent actual Docker gates required',
                    'source_commit':verified['commit'],'checks':checks}
            Path(args.report).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
            if report['status']!='PASS':raise RuntimeError('Native update acceptance failed')
        except Exception as failure:
            report={'status':'FAIL','source_commit':verified['commit'],'error_type':type(failure).__name__,
                    'reason':str(failure),'boundary':'native-macos-processes-dependencies-http'}
            Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
            if hasattr(runtime,'failed_command_output'):
                (Path(args.report).parent/'update-native-command.log').write_text(runtime.failed_command_output)
            for name in ('backend','frontend'):
                log=target/'.olympus/runtime'/(name+'.log')
                if log.is_file():
                    content=log.read_text(errors='replace')[-12000:]
                    for value in ('synthetic-update-only-password','synthetic-update-only-0123456789abcdef0123456789abcdef'):
                        content=content.replace(value,'SYNTHETIC_REDACTED')
                    (Path(args.report).parent/('update-native-'+name+'.log')).write_text(content)
            raise
        finally:
            runtime.stop(target)


if __name__=='__main__':main()
