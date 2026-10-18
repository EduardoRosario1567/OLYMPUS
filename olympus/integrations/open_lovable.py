"""Pilot-only Open Lovable adapter. The upstream is NOT multi-tenant: it
holds sandbox and conversation in process globals. Use a dedicated single
replica; the single-process lock below is not a distributed lock.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from olympus.agent.autonomous_developer import DeveloperReport
from olympus.agent.mission_compiler import MissionCompiler


class OpenLovableError(RuntimeError):
    pass


_SESSION_LOCK = threading.Lock()
_FILE_TAG = re.compile(r'<file\s+path="([^"]{1,220})">([\s\S]*?)</file>')
_MAX_GENERATED = 3 * 1024 * 1024
_MAX_EVENTS = 30000
_MAX_FILES = 80
_ALLOWED_EXT = {'.jsx', '.tsx', '.js', '.ts', '.css', '.html', '.json', '.svg', '.md'}


def _validated_base(raw: str) -> str:
    parsed = urlsplit(raw.strip())
    host = (parsed.hostname or '').lower()
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise OpenLovableError('Invalid upstream origin')
    if parsed.scheme == 'http' and (host.endswith('.railway.internal') or host in ('localhost', '127.0.0.1')):
        return raw.rstrip('/')
    if parsed.scheme == 'https' and host.endswith('.up.railway.app'):
        return raw.rstrip('/')
    raise OpenLovableError('Upstream must be an internal Railway origin, local test origin or Railway HTTPS domain')


def _safe_path(raw: str) -> Path:
    if '\\' in raw or '\x00' in raw or raw.startswith('/') or ':' in raw:
        raise OpenLovableError('Unsafe generated path')
    p = PurePosixPath(raw)
    if any(piece in ('..', '.', '') for piece in raw.split('/')) or p.suffix.lower() not in _ALLOWED_EXT:
        raise OpenLovableError('Unsafe generated path')
    if p.parts[0] not in ('src', 'public') and raw not in (
        'index.html', 'package.json', 'vite.config.js',
        'tailwind.config.js', 'postcss.config.js'
    ):
        raise OpenLovableError('Generated file outside web project')
    if len(p.parts) > 8:
        raise OpenLovableError('Generated path too deep')
    return Path(*p.parts)


def _files_from_generated(text: str) -> dict[Path, str]:
    if len(text.encode('utf-8')) > _MAX_GENERATED:
        raise OpenLovableError('Generated code too large')
    opens = len(re.findall(r'<file\s+path="', text))
    closes = text.count('</file>')
    if opens != closes:
        raise OpenLovableError('Incomplete file tags')
    files = {}
    for match in _FILE_TAG.finditer(text):
        p = _safe_path(match.group(1))
        if p in files:
            raise OpenLovableError('Duplicate generated path')
        files[p] = match.group(2).strip() + '\n'
        if len(files) > _MAX_FILES:
            raise OpenLovableError('Too many generated files')
    if not files or len(files) != opens:
        raise OpenLovableError('No complete generated files')
    if not any(str(path) in (
        'src/App.jsx', 'src/App.tsx', 'src/main.jsx', 'src/main.tsx', 'index.html'
    ) for path in files):
        raise OpenLovableError('No application entrypoint generated')
    return files


class OpenLovableClient:
    def __init__(self, url: str, model: str, *, user: str = '', password: str = '', timeout: int = 180):
        self.base = _validated_base(url)
        if not re.fullmatch(r'[a-zA-Z0-9._/-]{2,120}', model):
            raise OpenLovableError('Invalid model identifier')
        self.model = model
        self.timeout = min(max(int(timeout), 5), 240)
        self.user, self.password = user, password
        if self.base.startswith('https://') and not (user and password):
            raise OpenLovableError('HTTPS pilot proxy requires Basic credentials')

    def _open(self, path: str, payload: dict | None = None):
        headers = {'Accept': 'application/json, text/event-stream'}
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if self.user and self.password:
            token = base64.b64encode(f'{self.user}:{self.password}'.encode()).decode('ascii')
            headers['Authorization'] = 'Basic ' + token
        request = Request(self.base + path, data=data, headers=headers,
                          method='POST' if payload is not None else 'GET')
        try:
            return urlopen(request, timeout=self.timeout)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise OpenLovableError(f'Upstream transport failed ({type(exc).__name__})') from None

    def json(self, path: str, payload: dict | None = None) -> dict:
        with self._open(path, payload) as response:
            data = response.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            raise OpenLovableError('Upstream JSON exceeds limit')
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise OpenLovableError('Invalid upstream JSON') from None
        if not isinstance(result, dict):
            raise OpenLovableError('Invalid upstream response')
        if result.get('success') is False or result.get('error'):
            raise OpenLovableError('Upstream reported failure')
        return result

    def sse(self, path: str, payload: dict) -> dict:
        completed = None
        size = 0
        with self._open(path, payload) as response:
            for index, line in enumerate(response):
                if index > _MAX_EVENTS:
                    raise OpenLovableError('Upstream event limit exceeded')
                size += len(line)
                if size > 5 * 1024 * 1024:
                    raise OpenLovableError('Upstream stream too large')
                if not line.startswith(b'data: '):
                    continue
                try:
                    event = json.loads(line[6:])
                except (ValueError, UnicodeError):
                    raise OpenLovableError('Malformed upstream SSE event') from None
                if not isinstance(event, dict):
                    raise OpenLovableError('Malformed upstream SSE event')
                if event.get('type') == 'error':
                    raise OpenLovableError('Upstream stream failed')
                if event.get('type') == 'complete':
                    if completed is not None:
                        raise OpenLovableError('Multiple upstream completion events')
                    completed = event
        if completed is None:
            raise OpenLovableError('Upstream stream ended without completion')
        return completed


class OpenLovableWebDeveloper:
    """Web-only delegate preserving normal OLYMPUS missions for other tasks."""

    def __init__(self, workspace: str, default_runner, telemetry=None, *, client=None):
        self.workspace = Path(workspace).resolve()
        self.default_runner = default_runner
        self.telemetry = telemetry or (lambda _event: None)
        self.client = client

    def run(self, task: str, max_iterations: int = 12, resume: bool = True):
        if MissionCompiler().compile(task).task_family != 'web':
            return self.default_runner.run(task, max_iterations=max_iterations, resume=resume)
        # Only controlled single-writer pilot. No fallback after a remote
        # sandbox mutation, which would produce inconsistent deliverables.
        # Upstream uses global sandbox/conversation state, therefore production
        # MUST stay disabled regardless of feature flags until session isolation.
        if os.environ.get('OLYMPUS_ENV', 'development').lower() in ('production', 'prod'):
            return self._blocked(task, 'Open Lovable upstream is not tenant-isolated: production disabled')
        if os.getenv('OLYMPUS_OPEN_LOVABLE_EXCLUSIVE') != '1':
            return self._blocked(task, 'Dedicated single-replica Open Lovable required (pilot only)')
        if not _SESSION_LOCK.acquire(blocking=False):
            return self._blocked(task, 'Open Lovable pilot busy; retry later')
        try:
            return self._run_web(task)
        except (OpenLovableError, OSError, ValueError) as exc:
            return self._blocked(task, str(exc))
        finally:
            _SESSION_LOCK.release()

    @staticmethod
    def _blocked(task: str, error: str):
        return DeveloperReport(task, 'blocked', False, (), (), (), (), 0, error=error)

    def _run_web(self, task: str):
        client = self.client or OpenLovableClient(
            os.environ.get('OLYMPUS_OPEN_LOVABLE_URL', ''),
            os.environ.get('OLYMPUS_OPEN_LOVABLE_MODEL', ''),
            user=os.environ.get('OLYMPUS_OPEN_LOVABLE_USER', ''),
            password=os.environ.get('OLYMPUS_OPEN_LOVABLE_PASSWORD', ''),
        )
        self.telemetry({'event': 'open_lovable_started', 'engine': 'open_lovable', 'pilot': True})
        sandbox = client.json('/api/create-ai-sandbox-v2', {})
        sid = sandbox.get('sandboxId')
        if not isinstance(sid, str) or not sid or len(sid) > 200:
            raise OpenLovableError('Sandbox ID missing')
        self.telemetry({'event': 'open_lovable_sandbox_ready'})
        generated = client.sse('/api/generate-ai-code-stream', {
            'prompt': task, 'model': client.model, 'context': {'sandboxId': sid}, 'isEdit': False,
        })
        code = generated.get('generatedCode')
        if not isinstance(code, str):
            raise OpenLovableError('Generated code missing')
        files = _files_from_generated(code)
        applied = client.sse('/api/apply-ai-code-stream', {
            'response': code, 'isEdit': False, 'packages': [], 'sandboxId': sid,
        })
        results = applied.get('results')
        if not isinstance(results, dict) or results.get('errors') or not (
            results.get('filesCreated') or results.get('filesUpdated')
        ):
            raise OpenLovableError('Remote sandbox did not apply files')
        expected_files = {str(p) for p in files}
        actual_files = {str(p) for p in (
            list(results.get('filesCreated') or ()) + list(results.get('filesUpdated') or ())
        )}
        if not expected_files.issubset(actual_files):
            raise OpenLovableError('Sandbox reported incomplete file application')
        # The upstream E2B provider may report exitCode=0 even when npm exits
        # nonzero; require the explicit subprocess Return code marker as well.
        build = client.json('/api/run-command-v2', {'command': 'npm run build'})
        output = str(build.get('output') or '')
        if (build.get('success') is not True or build.get('exitCode') != 0
                or not re.search(r'(?m)^Return code:\s*0\s*$', output)):
            raise OpenLovableError('React build did not pass inside sandbox')
        self.telemetry({'event': 'open_lovable_build_passed', 'sandbox': 'e2b'})
        root = self.workspace
        root.mkdir(parents=True, exist_ok=True)
        for relative, content in files.items():
            target = root / relative
            if not target.resolve().is_relative_to(root):
                raise OpenLovableError('Output escaped execution workspace')
            if any(parent.is_symlink() for parent in (target, *target.parents)
                   if parent != root and parent.is_relative_to(root)):
                raise OpenLovableError('Refusing generated symlink target')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        main_file = 'src/main.tsx' if (root / 'src/main.tsx').exists() else 'src/main.jsx'
        if not (root / 'index.html').exists():
            (root / 'index.html').write_text(
                '<!doctype html><html lang="pt-BR"><head><meta charset="UTF-8"/>'
                '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
                '</head><body><div id="root"></div>'
                '<script type="module" src="/' + main_file + '"></script></body></html>\n',
                encoding='utf-8'
            )
        if not (root / 'src/main.jsx').exists() and not (root / 'src/main.tsx').exists():
            (root / 'src').mkdir(exist_ok=True)
            (root / 'src/main.jsx').write_text(
                "import React from 'react';\nimport { createRoot } from 'react-dom/client';\n"
                "import App from './App." + ("tsx" if (root / 'src/App.tsx').exists() else "jsx") + "';\n"
                "createRoot(document.getElementById('root')).render(<App />);\n",
                encoding='utf-8'
            )
        if not (root / 'package.json').exists():
            (root / 'package.json').write_text(json.dumps({
                'name': 'olympus-lovable-delivery', 'version': '0.1.0', 'private': True,
                'type': 'module', 'scripts': {'dev': 'vite --host 0.0.0.0', 'build': 'vite build'},
                'dependencies': {'react': '^19.0.0', 'react-dom': '^19.0.0'},
                'devDependencies': {'vite': '^6.0.0'},
            }, indent=2) + '\n', encoding='utf-8')
        output = list(files)
        for name in ('index.html', 'package.json', 'src/main.jsx'):
            if Path(name) not in output and (root / name).exists():
                output.append(Path(name))
        concept = root / 'docs/delivery-concept.md'
        concept.parent.mkdir(parents=True, exist_ok=True)
        if not concept.exists():
            concept.write_text(
                '# OLYMPUS — Web delivery concept\n\n'
                '## Visual thesis\nAI-generated React interface; browser/visual review pending.\n\n'
                '## Content plan\nOriginal user request is the source; no external facts verified.\n\n'
                '## Interaction plan\nResponsive React application; interactions require browser verification.\n\n'
                '## Evidence\nOpen Lovable protocol completed; independent OLYMPUS checks pending. '
                'No visual test evidence; image source/license checks pending.\n',
                encoding='utf-8'
            )
            output.append(Path('docs/delivery-concept.md'))
        self.telemetry({'event': 'open_lovable_files_ready', 'count': len(output)})
        return DeveloperReport(
            task, 'completed', True, (client.model,), (), tuple(str(p) for p in output),
            ('sandbox_react_build',), 1,
            delivery_review={'engine': 'open_lovable', 'build': 'passed_remote', 'browser': 'pending'}
        )
