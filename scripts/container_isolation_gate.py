#!/usr/bin/env python3
"""Actual Docker negative tests. No mocks, package install, or host fallback."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from olympus.agent.container_execution import ContainerExecutor


def main():
    with tempfile.TemporaryDirectory(prefix='olympus-isolation-proof-') as directory:
        private = Path(directory)/'private-host-marker'
        private.write_text('SYNTHETIC_HOST_SECRET')
        project = Path(directory)/'project'; project.mkdir()
        (project/'.env').write_text('SYNTHETIC_PROJECT_SECRET')
        (project/'delivery.txt').write_text('UNCHANGED')
        code = '''import json,os,pathlib,socket
checks={}
checks['unprivileged']=os.getuid()!=0
checks['host_secret_hidden']=not pathlib.Path(__HOST_SECRET__).exists()
checks['project_env_excluded']=not pathlib.Path('/workspace/.env').exists()
checks['docker_socket_hidden']=not pathlib.Path('/var/run/docker.sock').exists()
checks['provider_env_absent']=not any(k in os.environ for k in ['OPENAI_API_KEY','OMNIROUTE_API_KEY','OLYMPUS_JWT_SECRET','HTTPS_PROXY'])
for key,path in [('workspace_readonly','/workspace/delivery.txt'),('root_readonly','/etc/olympus-denied')]:
    try:
        pathlib.Path(path).write_text('MUTATED');checks[key]=False
    except OSError:checks[key]=True
try:
    sock=socket.create_connection(('1.1.1.1',443),timeout=1);sock.close();checks['network_denied']=False
except OSError:checks['network_denied']=True
pathlib.Path('/tmp/allowed').write_text('temporary')
checks['temporary_writes_allowed']=pathlib.Path('/tmp/allowed').read_text()=='temporary'
print(json.dumps(checks))
raise SystemExit(0 if all(checks.values()) else 1)
'''.replace('__HOST_SECRET__',repr(str(private)))
        result = ContainerExecutor().run(project, [sys.executable,'-c',code], 20)
        try: checks = json.loads(result.stdout)
        except (ValueError,TypeError): checks = {}
        status = 'PASS' if result.returncode==0 and len(checks)==9 and all(value is True for value in checks.values()) else 'BLOCKED' if result.returncode==125 else 'FAIL'
        if (project/'delivery.txt').read_text()!='UNCHANGED' or private.read_text()!='SYNTHETIC_HOST_SECRET':
            status='FAIL'
        report={'gate':'container-isolation-v1','status':status,'generated_at':datetime.now(timezone.utc).isoformat(),
            'boundary':'actual-local-docker','checks':checks,'returncode':result.returncode,'diagnostic':result.stderr[-1500:]}
    destination=ROOT/'.olympus/qa/container-isolation-gate.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if status=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
