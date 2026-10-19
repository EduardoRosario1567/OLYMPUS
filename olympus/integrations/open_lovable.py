"""Pilot-only Open Lovable adapter. The upstream is NOT multi-tenant: it
holds sandbox and conversation in process globals. Use a dedicated single
replica; the single-process lock below is not a distributed lock.
"""
from __future__ import annotations

import base64
import hashlib
import json
import fcntl
import stat
import os
import re
import threading
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from olympus.agent.autonomous_developer import DeveloperReport
from olympus.agent.mission_compiler import MissionCompiler


class OpenLovableError(RuntimeError):
    pass


class IncompleteGeneratedCode(OpenLovableError):
    """An incomplete response may be retried before any remote mutation."""


_SESSION_LOCK = threading.Lock()
_FILE_TAG = re.compile(r'<file\s+path="([^"]{1,220})">([\s\S]*?)</file>')
_MAX_GENERATED = 3 * 1024 * 1024
_MAX_EVENTS = 30000
_MAX_FILES = 80
_ALLOWED_EXT = {'.jsx', '.tsx', '.js', '.ts', '.css', '.html', '.json', '.svg', '.md'}



def pilot_tenant_authorized(actual_tenant: str | None, allowed_tenant: str | None) -> bool:
    """Explicit tenant allowlist before opening a shared experimental upstream."""
    return bool(actual_tenant and allowed_tenant and
                str(actual_tenant).strip() == str(allowed_tenant).strip())


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
    if any(piece.startswith('.') for piece in p.parts):
        raise OpenLovableError('Hidden source paths are not exportable')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', raw):
        raise OpenLovableError('Unexpected generated path characters')
    if p.parts[0] not in ('src', 'public') and raw not in (
        'index.html', 'package.json', 'package-lock.json', 'tsconfig.json',
        'vite.config.js', 'vite.config.ts', 'tailwind.config.js',
        'tailwind.config.ts', 'postcss.config.js', 'postcss.config.ts',
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
        raise IncompleteGeneratedCode('Incomplete file tags')
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


def _command_passed(result: dict) -> bool:
    """E2B's API exit code is not the child-process exit code."""
    output = str(result.get('output') or '')
    final = re.search(r'(?:^|\n)Return code:\s*(-?\d+)\s*\Z', output)
    return (result.get('success') is True and type(result.get('exitCode')) is int
            and result['exitCode'] == 0 and final is not None
            and final.group(1) == '0')


def _entrypoint_restore_command(proposed: dict[Path, str]) -> str | None:
    """Restore generated entrypoints that upstream's applicator rewrites.

    The fixed writer runs only inside the already selected E2B sandbox. Its
    sole argument has no spaces: upstream runCommand uses command.split(' '),
    not shell parsing. Model content is JSON/base64 data, never executable
    writer code. No generated package scripts or dependencies are changed.
    """
    names = {'index.html', 'src/main.jsx', 'src/main.tsx'}
    entries = {str(path): content for path, content in proposed.items()
               if str(path) in names}
    if not entries:
        return None
    payload = base64.b64encode(json.dumps(entries, ensure_ascii=False).encode()).decode()
    writer = (
        "const fs=require('fs'),p=require('path');"
        "const data=JSON.parse(Buffer.from('" + payload + "','base64').toString('utf8'));"
        "for(const [name,body]of Object.entries(data)){"
        "const root=fs.realpathSync('.'),target=fs.realpathSync(name);"
        "if(target!==p.resolve(root,name)||!fs.lstatSync(name).isFile())"
        "throw Error('unsafe_entrypoint');fs.writeFileSync(name,body,'utf8');}"
        "console.log('OLYMPUS_ENTRYPOINTS_RESTORED');"
    )
    encoded = base64.b64encode(writer.encode()).decode()
    # Keep below Linux's per-argument limit and reject rather than truncate.
    if len(encoded) > 100000:
        raise OpenLovableError('Entrypoint restoration exceeds command size limit')
    return "node -e eval(Buffer.from('" + encoded + "','base64').toString('utf8'))"


def _verify_presentation_sources(files: dict[Path, str], proposed: dict[Path, str]) -> None:
    """Catch known compile-green/source-broken failures; not a visual review."""
    for path, content in proposed.items():
        if str(path) in {'index.html', 'src/main.jsx', 'src/main.tsx'}:
            if files.get(path, '').strip() != content.strip():
                raise OpenLovableError('Generated entrypoint changed during application: ' + str(path))
    # The applicator has removed stylesheet imports from real missions.
    # Check every explicitly generated relative CSS import against the snapshot.
    css_import = re.compile(r"\bimport\s+(?:[^;\n'\"]+?\s+from\s+)?(['\"])(\.[^'\"\n]*\.css)\1")
    for path, original in proposed.items():
        if path.suffix not in {'.js', '.jsx', '.ts', '.tsx'}:
            continue
        expected = {match.group(2) for match in css_import.finditer(original)}
        actual = {match.group(2) for match in css_import.finditer(files.get(path, ''))}
        if not expected.issubset(actual):
            raise OpenLovableError('Stylesheet import removed during application: ' + str(path))
        for specifier in expected:
            parts = list(path.parent.parts)
            for part in PurePosixPath(specifier).parts:
                if part == '..':
                    if not parts:
                        raise OpenLovableError('Stylesheet import escapes project')
                    parts.pop()
                elif part != '.':
                    parts.append(part)
            target = _safe_path('/'.join(parts))
            if target not in files:
                raise OpenLovableError('Imported stylesheet missing from export: ' + str(target))


@contextmanager
def _pilot_process_lock():
    """Fail-closed same-host advisory lease; NOT a distributed tenant lock."""
    base = Path(os.getenv('OLYMPUS_OPEN_LOVABLE_LOCK_DIR') or
                (Path(os.getenv('OLYMPUS_CLOUD_DATA_DIR', '.olympus/cloud')) /
                 'locks')).resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = base.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise OpenLovableError('Pilot lock directory is not private')
    lock_path = base / 'open-lovable.lock'
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise OpenLovableError('Pilot lock file is not private')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OpenLovableError('Open Lovable pilot held by another local worker') from None
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


class OpenLovableClient:
    def __init__(self, url: str, model: str, *, user: str = '', password: str = '',
                 export_token: str = '', timeout: int = 180):
        self.base = _validated_base(url)
        if not re.fullmatch(r'[a-zA-Z0-9._/-]{2,120}', model):
            raise OpenLovableError('Invalid model identifier')
        self.model = model
        self.timeout = min(max(int(timeout), 5), 240)
        self.user, self.password = user, password
        self.export_token = export_token
        if self.base.startswith('https://') and not (user and password):
            raise OpenLovableError('HTTPS pilot proxy requires Basic credentials')

    def _open(self, path: str, payload: dict | None = None):
        headers = {'Accept': 'application/json, text/event-stream'}
        data = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if path == '/api/olympus-export':
            if len(self.export_token) < 32:
                raise OpenLovableError('Private export token is not configured')
            headers['X-Olympus-Bridge-Token'] = self.export_token
        if self.user and self.password:
            token = base64.b64encode(f'{self.user}:{self.password}'.encode()).decode('ascii')
            headers['Authorization'] = 'Basic ' + token
        request = Request(self.base + path, data=data, headers=headers,
                          method='POST' if payload is not None else 'GET')
        try:
            return urlopen(request, timeout=self.timeout)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise OpenLovableError(f'Upstream transport failed ({type(exc).__name__})') from None

    def json(self, path: str, payload: dict | None = None, *, max_bytes: int = 128 * 1024) -> dict:
        limit = min(max(int(max_bytes), 1024), 5 * 1024 * 1024)
        with self._open(path, payload) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
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


def _verify_export(response: dict, sandbox_id: str, proposed: set[str]) -> tuple[dict[Path, str], str]:
    """Validate an authoritative UTF-8 source snapshot; reject missing/unsafe files."""
    if response.get('success') is not True or response.get('sandboxId') != sandbox_id:
        raise OpenLovableError('Sandbox export identity mismatch')
    raw = response.get('files')
    if not isinstance(raw, list) or not 1 <= len(raw) <= _MAX_FILES:
        raise OpenLovableError('Invalid export file count')
    accepted: dict[Path, str] = {}
    total = 0
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise OpenLovableError('Malformed exported file')
        path = _safe_path(item['path'])
        if path in accepted:
            raise OpenLovableError('Duplicate exported file')
        body, checksum = item.get('content'), item.get('sha256')
        if not isinstance(body, str) or not isinstance(checksum, str):
            raise OpenLovableError('Exported file lacks integrity evidence')
        encoded = body.encode('utf-8')
        if len(encoded) > 512 * 1024:
            raise OpenLovableError('Exported file exceeds size limit')
        total += len(encoded)
        if total > _MAX_GENERATED:
            raise OpenLovableError('Exported project exceeds size limit')
        if hashlib.sha256(encoded).hexdigest() != checksum:
            raise OpenLovableError('Exported file checksum mismatch')
        accepted[path] = body
    names = {str(x) for x in accepted}
    if not proposed.issubset(names):
        raise OpenLovableError('Sandbox export is missing generated files')
    if ('index.html' not in names or 'package.json' not in names
            or not names.intersection({'src/main.jsx', 'src/main.tsx'})):
        raise OpenLovableError('Sandbox export lacks Vite entrypoints')
    try:
        package = json.loads(accepted[Path('package.json')])
    except (KeyError, ValueError, TypeError):
        raise OpenLovableError('Invalid exported package manifest') from None
    if not isinstance(package, dict) or 'build' not in package.get('scripts', {}):
        raise OpenLovableError('Exported project lacks build script')
    digest = hashlib.sha256()
    for path in sorted(accepted, key=str):
        digest.update(str(path).encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(accepted[path].encode('utf-8')).digest())
    if digest.hexdigest() != response.get('sha256'):
        raise OpenLovableError('Exported project manifest checksum mismatch')
    return accepted, digest.hexdigest()


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
            # Filesystem advisory lease protects multiple workers on ONE host,
            # never across isolated Railway replicas.
            with _pilot_process_lock():
                return self._run_web(task)
        except (OpenLovableError, OSError, ValueError) as exc:
            return self._blocked(task, str(exc))
        finally:
            _SESSION_LOCK.release()


    @staticmethod
    def _confirm_sandbox(client, sid: str) -> None:
        result = client.json('/api/sandbox-status')
        current = result.get('sandboxData')
        if (not result.get('active') or not result.get('healthy')
                or not isinstance(current, dict) or current.get('sandboxId') != sid):
            raise OpenLovableError('Active sandbox changed during mission')

    @staticmethod
    def _blocked(task: str, error: str):
        return DeveloperReport(task, 'blocked', False, (), (), (), (), 0, error=error)

    def _run_web(self, task: str):
        client = self.client or OpenLovableClient(
            os.environ.get('OLYMPUS_OPEN_LOVABLE_URL', ''),
            os.environ.get('OLYMPUS_OPEN_LOVABLE_MODEL', ''),
            user=os.environ.get('OLYMPUS_OPEN_LOVABLE_USER', ''),
            password=os.environ.get('OLYMPUS_OPEN_LOVABLE_PASSWORD', ''),
            export_token=os.environ.get('OLYMPUS_OPEN_LOVABLE_EXPORT_TOKEN', ''),
        )
        self.telemetry({'event': 'open_lovable_started', 'engine': 'open_lovable', 'pilot': True})
        sandbox = client.json('/api/create-ai-sandbox-v2', {})
        sid = sandbox.get('sandboxId')
        if not isinstance(sid, str) or not sid or len(sid) > 200:
            raise OpenLovableError('Sandbox ID missing')
        self.telemetry({'event': 'open_lovable_sandbox_ready'})
        prompt = task
        for attempt in range(2):
            generated = client.sse('/api/generate-ai-code-stream', {
                'prompt': prompt, 'model': client.model, 'context': {'sandboxId': sid}, 'isEdit': False,
            })
            code = generated.get('generatedCode')
            if not isinstance(code, str):
                raise OpenLovableError('Generated code missing')
            try:
                proposed_files = _files_from_generated(code)
                break
            except IncompleteGeneratedCode:
                if attempt:
                    raise
                self.telemetry({'event': 'open_lovable_generation_retry',
                                'reason': 'incomplete_file_tags', 'attempt': 2})
                prompt = (task + '\n\nThe previous response was truncated. Regenerate the COMPLETE '
                          'files using closed <file path="...">...</file> blocks. '
                          'Use concise complete code, no commentary and no unfinished sections.')
        applied = client.sse('/api/apply-ai-code-stream', {
            'response': code, 'isEdit': False, 'packages': [], 'sandboxId': sid,
        })
        results = applied.get('results')
        if not isinstance(results, dict) or results.get('errors') or not (
            results.get('filesCreated') or results.get('filesUpdated')
        ):
            raise OpenLovableError('Remote sandbox did not apply files')
        expected_files = {str(p) for p in proposed_files}
        actual_files = {str(p) for p in (
            list(results.get('filesCreated') or ()) + list(results.get('filesUpdated') or ())
        )}
        if not expected_files.issubset(actual_files):
            raise OpenLovableError('Sandbox reported incomplete file application')
        # The upstream uses global process state: check the sandbox identity
        # before build and again after the authoritative source export.
        self._confirm_sandbox(client, sid)
        restore = _entrypoint_restore_command(proposed_files)
        if restore is not None:
            restored = client.json('/api/run-command-v2', {'command': restore})
            if (not _command_passed(restored) or
                    'OLYMPUS_ENTRYPOINTS_RESTORED' not in str(restored.get('output') or '')):
                raise OpenLovableError('Generated entrypoints could not be preserved')
            self._confirm_sandbox(client, sid)
            self.telemetry({'event': 'open_lovable_entrypoints_preserved'})
        # E2B runCommand currently wraps subprocess and reports a generic
        # success even when npm fails: parse the subprocess return code too.
        build = client.json('/api/run-command-v2', {'command': 'npm run build'})
        if not _command_passed(build):
            raise OpenLovableError('React build did not pass inside sandbox')
        self.telemetry({'event': 'open_lovable_build_passed', 'sandbox': 'e2b'})
        # Contract requires a patched dedicated upstream. Vanilla
        # /api/create-zip references a different global sandbox variable,
        # and /api/get-sandbox-files also uses the wrong global.
        try:
            export = client.json(
                '/api/olympus-export', {'sandboxId': sid},
                max_bytes=5 * 1024 * 1024,
            )
        except (OpenLovableError, TypeError) as exc:
            raise OpenLovableError('Sandbox export unavailable or incompatible') from exc
        files, digest = _verify_export(export, sid, expected_files)
        _verify_presentation_sources(files, proposed_files)
        self._confirm_sandbox(client, sid)
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
        output = list(files)
        self.telemetry({
            'event': 'open_lovable_export_verified',
            'files': len(files),
            'sha256': digest,
        })
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
            ('sandbox_react_build', 'export_source_integrity'), attempt + 1,
            delivery_review={'engine': 'open_lovable', 'build': 'passed_remote',
                             'export_sha256': digest, 'browser': 'pending',
                             'source_integrity': 'passed',
                             'scope': 'source_and_build_only', 'visual': 'pending'}
        )
