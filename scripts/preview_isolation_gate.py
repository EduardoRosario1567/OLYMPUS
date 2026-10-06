#!/usr/bin/env python3
"""Mandatory real-preview qualification. CLI has no mocks, install or host fallback."""
from __future__ import annotations
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from olympus.cloud.preview_container import PreviewContainerExecutor, PreviewLifecycleError

FRAMEWORKS = ('Next.js', 'Vite', 'React')
MARKER = 'OLYMPUS_PREVIEW_QUALIFICATION'
STDOUT_MARKER = 'OLYMPUS_PREVIEW_STDOUT_PROBE'
STDERR_MARKER = 'OLYMPUS_PREVIEW_STDERR_PROBE'
PROBE_KEYS = frozenset({'unprivileged', 'host_marker_hidden', 'project_env_excluded',
    'docker_socket_hidden', 'provider_env_absent', 'snapshot_readonly', 'root_readonly',
    'private_work_writable', 'network_denied', 'launch_matches_reviewed_source',
    'fetch_matches_reviewed_source', 'stdout_probe_written', 'stderr_probe_written'})


class ScriptAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            value = dict(attrs).get('src', '')
            if value.startswith('/') and not value.startswith('//') and len(self.paths)<20:
                self.paths.append(value)


def fixture(root, framework):
    root.mkdir()
    packages = {'Next.js': 'next', 'Vite': 'vite', 'React': 'react-scripts'}
    (root/'package.json').write_text(json.dumps({'private': True,
        'dependencies': {packages[framework]: '*'}, 'scripts': {'dev': 'never invoked'}}))
    (root/'.env').write_text('SYNTHETIC_PROJECT_SECRET')
    (root/'unchanged.txt').write_text('UNCHANGED')
    if framework == 'Next.js':
        (root/'app').mkdir()
        (root/'app/layout.jsx').write_text('export default function Layout({children}) { return <html><body>{children}</body></html>; }')
        (root/'app/page.jsx').write_text('export default function Page() { return <main>'+MARKER+'</main>; }')
    elif framework == 'Vite':
        (root/'index.html').write_text('<html><body><main>'+MARKER+'</main><script type="module" src="/main.js"></script></body></html>')
        (root/'main.js').write_text('console.log("preview qualification module");')
    else:
        (root/'public').mkdir(); (root/'src').mkdir()
        (root/'public/index.html').write_text('<html><body><main>'+MARKER+'</main><div id="root"></div></body></html>')
        (root/'src/index.js').write_text('import React from "react"; import {createRoot} from "react-dom/client"; createRoot(document.getElementById("root")).render(React.createElement("p",null,"React qualification"));')


def actual_probe(executor, handle, private_marker):
    expected = {name: sha256((ROOT/'containers'/name).read_bytes()).hexdigest()
        for name in ('preview-launch.mjs', 'preview-fetch.mjs')}
    config = json.dumps({'host': str(private_marker), 'expected': expected,
        'stdout': STDOUT_MARKER, 'stderr': STDERR_MARKER})
    program = r'''const fs=require('fs'),net=require('net'),crypto=require('crypto');
const config=CONFIG, checks={};
checks.unprivileged=process.getuid()!==0;
checks.host_marker_hidden=!fs.existsSync(config.host);
checks.project_env_excluded=!fs.existsSync('/snapshot/.env');
checks.docker_socket_hidden=!fs.existsSync('/var/run/docker.sock');
checks.provider_env_absent=!['OPENAI_API_KEY','OMNIROUTE_API_KEY','OLYMPUS_JWT_SECRET','HTTPS_PROXY'].some(k=>k in process.env);
for(const [key,file] of [['snapshot_readonly','/snapshot/unchanged.txt'],['root_readonly','/etc/olympus-preview-denied']]){
 try{fs.writeFileSync(file,'MUTATED');checks[key]=false;}catch{checks[key]=true;}
}
try{fs.writeFileSync('/work/qualification-allowed','temporary');checks.private_work_writable=fs.readFileSync('/work/qualification-allowed','utf8')==='temporary';}catch{checks.private_work_writable=false;}
for(const [key,name] of [['launch_matches_reviewed_source','preview-launch.mjs'],['fetch_matches_reviewed_source','preview-fetch.mjs']]){
 try{checks[key]=crypto.createHash('sha256').update(fs.readFileSync('/opt/olympus-preview/'+name)).digest('hex')===config.expected[name];}catch{checks[key]=false;}
}
for(const [key,fd,message] of [['stdout_probe_written','1',config.stdout],['stderr_probe_written','2',config.stderr]]){
 try{fs.writeFileSync('/proc/1/fd/'+fd,message+'\n');checks[key]=true;}catch{checks[key]=false;}
}
let finished=false;const socket=net.connect({host:'1.1.1.1',port:443});
function finish(denied){if(finished)return;finished=true;socket.destroy();checks.network_denied=denied;process.stdout.write(JSON.stringify(checks));}
socket.setTimeout(1000,()=>finish(true));socket.on('error',()=>finish(true));socket.on('connect',()=>finish(false));
'''.replace('CONFIG', config)
    response = executor._capture_http([*handle.client, 'exec', '--user=65534:65534',
        handle.name, '/usr/local/bin/node', '-e', program], timeout_seconds=5,
        output_limit=16384, stderr_limit=16384, stderr_tail=False)
    if response.returncode:
        raise RuntimeError('qualification probe did not complete')
    value = json.loads(response.stdout)
    if not isinstance(value, dict) or set(value) != PROBE_KEYS or any(type(x) is not bool for x in value.values()):
        raise ValueError('invalid qualification probe schema')
    return value


def qualify(executor, directory, timeout_seconds=30, probe=actual_probe):
    if not 0 < timeout_seconds <= 30:
        raise ValueError('invalid qualification deadline')
    directory = Path(directory)
    private = directory/'private-host-marker'
    private.write_text('SYNTHETIC_HOST_SECRET')
    results = []
    for index, framework in enumerate(FRAMEWORKS):
        root = directory/('project-'+str(index)); fixture(root, framework)
        original = {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
        handle = None
        item = {'framework': framework, 'status': 'FAIL', 'checks': {}}
        try:
            handle = executor.start(root, framework)
            item['image_id'] = handle.image_id
            checks = probe(executor, handle, private)
            if set(checks) != PROBE_KEYS or any(type(x) is not bool for x in checks.values()):
                raise ValueError('invalid qualification checks')
            item['checks'].update(checks)
            if not all(checks.values()):
                raise RuntimeError('preview isolation or reviewed helpers failed qualification')
            ready = False
            deadline = time.monotonic()+timeout_seconds
            while time.monotonic()<deadline:
                try:
                    status, headers, body = executor.fetch(handle)
                    if 200<=status<300 and 'text/html' in headers.get('Content-Type','').lower() and MARKER.encode() in body:
                        ready = True; break
                except PreviewLifecycleError:
                    pass
                time.sleep(min(.2,max(0,deadline-time.monotonic())))
            item['checks']['framework_http_ready'] = ready
            asset_ready = False
            if ready:
                parser = ScriptAssets();parser.feed(body.decode('utf-8',errors='replace'))
                if parser.paths:
                    asset_path, _, query = parser.paths[0].partition('?')
                    status, headers, asset = executor.fetch(handle, asset_path, query)
                    asset_ready = (200<=status<300 and bool(asset.strip()) and
                        any(kind in headers.get('Content-Type','').lower() for kind in ('application/javascript','text/javascript')))
            item['checks']['javascript_asset_ready'] = asset_ready
            logs = executor.logs(handle)
            item['checks']['stdout_observed'] = any(stream=='stdout' and STDOUT_MARKER in message for _,stream,message in logs)
            item['checks']['stderr_observed'] = any(stream=='stderr' and STDERR_MARKER in message for _,stream,message in logs)
        except PreviewLifecycleError as exc:
            handle = handle or exc.handle
            item.update(status='BLOCKED', diagnostic=str(exc))
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            item['diagnostic'] = type(exc).__name__
        finally:
            item['checks']['cleanup_confirmed'] = bool(handle and executor.stop(handle))
            if handle and not item['checks']['cleanup_confirmed']:
                item['status'] = 'BLOCKED'
            after = {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            item['checks']['original_project_preserved'] = after == original
            try:
                item['checks']['host_marker_preserved'] = private.read_text() == 'SYNTHETIC_HOST_SECRET'
            except OSError:
                item['checks']['host_marker_preserved'] = False
        if item['status']!='BLOCKED':
            item['status'] = 'PASS' if len(item['checks'])==20 and all(item['checks'].values()) else 'FAIL'
        results.append(item)
        if item['status']!='PASS':
            break
    status = 'PASS' if len(results)==len(FRAMEWORKS) and all(x['status']=='PASS' for x in results) else 'BLOCKED' if any(x['status']=='BLOCKED' for x in results) else 'FAIL'
    return {'gate':'preview-isolation-v1', 'boundary':'actual-local-docker', 'status':status,
        'required_frameworks':list(FRAMEWORKS), 'frameworks':results}


def main():
    executor = PreviewContainerExecutor()
    try:
        with tempfile.TemporaryDirectory(prefix='olympus-preview-proof-') as directory:
            report = qualify(executor, directory)
    finally:
        executor.close()
    destination = ROOT/'.olympus/qa/preview-isolation-gate.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
