"""Isolated preview lifecycle with durable, verified cleanup after restart.

Requires a pre-provisioned image with a reviewed /opt/olympus-preview/launch.mjs
entrypoint. Starting a Docker process does not certify HTTP readiness or OS
isolation. No image pull, installation, host-code execution or port publishing.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from threading import RLock, Thread, Event
from urllib.parse import unquote
import uuid

from olympus.agent.container_execution import ContainerExecutor, IsolationUnavailable, snapshot_project
from olympus.cloud.preview_journal import PreviewJournal, PreviewWorkspace

PREVIEW_IMAGE = "olympus-preview-runner:3.0.8-candidate"
PREVIEW_ROLE = "org.olympus.preview-runner"
PREVIEW_OWNER = "org.olympus.preview-owner"
FRAMEWORKS = {"Next.js": "next", "Vite": "vite", "React": "react"}
MAX_HTTP_BODY = 20 * 1024 * 1024
MAX_HTTP_ENVELOPE = ((MAX_HTTP_BODY + 2) // 3) * 4 + 16384


@dataclass
class PreviewContainer:
    name: str
    client: tuple
    image_id: str
    temporary: PreviewWorkspace
    status: str = "creating"
    cleanup_confirmed: bool = False


class PreviewLifecycleError(IsolationUnavailable):
    def __init__(self, message, handle=None):
        super().__init__(message)
        self.handle = handle


class PreviewContainerExecutor:
    """Owned containers only; failed cleanup retains the snapshot for retry."""

    def __init__(self, journal_root=None):
        self._pending = {}
        self._lock = RLock()
        self._journal = PreviewJournal(journal_root or Path(__file__).resolve().parents[2] / '.olympus/runtime/preview-containers')
        self._recovered = False

    def recover(self, client=None):
        """Revoke old executions; never restore browser tokens or trust saved clients."""
        with self._lock:
            if self._recovered:
                return
            self._journal.acquire()
            records = self._journal.records()
            if records:
                client = client or ContainerExecutor._client()
            for name, image_id in records.items():
                handle = self._pending.get(name)
                if handle is None:
                    handle = PreviewContainer(name, client, image_id, PreviewWorkspace(self._journal, name), 'cleanup_unconfirmed')
                    self._pending[name] = handle
                if not self.stop(handle):
                    raise PreviewLifecycleError('preview recovery cleanup_unconfirmed: ' + name, handle)
            self._recovered = True

    def close(self):
        with self._lock:
            try:
                for handle in tuple(self._pending.values()):
                    self.stop(handle)
            finally:
                if not self._pending:
                    self._journal.release()
                    self._recovered = False

    @staticmethod
    def _call(client, *arguments):
        return subprocess.run([*client, *arguments], capture_output=True, text=True,
            timeout=10, shell=False, env=ContainerExecutor._environment())

    def _image_id(self, client):
        response = self._call(client, "image", "inspect", PREVIEW_IMAGE)
        try:
            records = json.loads(response.stdout)
            if response.returncode or len(records) != 1:
                raise ValueError()
            record = records[0]
            image_id = record["Id"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
                raise ValueError()
            if record.get("Config", {}).get("Labels", {}).get(PREVIEW_ROLE) != "v1":
                raise ValueError()
            return image_id
        except (ValueError, TypeError, KeyError, AttributeError):
            raise IsolationUnavailable("approved preview image is unavailable or invalid")

    @staticmethod
    def _package_path(value):
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise IsolationUnavailable("invalid preview package path")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or any(p.startswith(".") for p in path.parts):
            raise IsolationUnavailable("invalid preview package path")
        if value != "." and path.as_posix() != value:
            raise IsolationUnavailable("noncanonical preview package path")
        return value

    def _inspect(self, handle):
        response = self._call(handle.client, "container", "inspect", handle.name)
        absent = response.returncode == 1 and bool(re.search(
            r"No such (?:container|object):\s*" + re.escape(handle.name) + r"\s*$", response.stderr or ""))
        if absent:
            return None
        try:
            records = json.loads(response.stdout)
            if response.returncode or len(records) != 1:
                raise ValueError()
            record = records[0]
            labels = record["Config"]["Labels"]
            if (record["Name"] != "/" + handle.name or record["Image"] != handle.image_id
                    or labels.get(PREVIEW_ROLE) != "v1" or labels.get(PREVIEW_OWNER) != handle.name):
                raise ValueError()
            if not isinstance(record.get("State", {}).get("Running"), bool):
                raise ValueError()
            return record
        except (ValueError, TypeError, KeyError, AttributeError):
            raise IsolationUnavailable("preview container ownership could not be verified")

    def start(self, root, framework, package_path="."):
        handle = None
        try:
            package_path = self._package_path(package_path)
            if not isinstance(framework, str) or framework not in FRAMEWORKS:
                raise IsolationUnavailable("unsupported preview framework")
            if Path(root).is_symlink():
                raise IsolationUnavailable("linked preview root is not supported")
            client = ContainerExecutor._client()
            self.recover(client)
            if self.pending():
                raise IsolationUnavailable('preview cleanup remains unconfirmed')
            image_id = self._image_id(client)
            name = "olympus-preview-" + uuid.uuid4().hex
            try:
                temporary = self._journal.create(name, image_id)
            except BaseException:
                self._recovered = False
                raise
            handle = PreviewContainer(name, client, image_id, temporary)
            with self._lock:
                self._pending[handle.name] = handle
            snapshot = Path(temporary.name) / "project"
            snapshot_project(root, snapshot)
            if not (snapshot / package_path / "package.json").is_file():
                raise IsolationUnavailable("preview package.json is absent from snapshot")
            argv = ["create", "--pull=never", "--name", handle.name,
                "--label", PREVIEW_ROLE + "=v1", "--label", PREVIEW_OWNER + "=" + handle.name,
                "--network=none", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true", "--user=65534:65534",
                "--pids-limit=128", "--memory=1024m", "--memory-swap=1024m", "--cpus=1",
                "--ulimit=nofile=256:256", "--log-driver=local",
                "--log-opt=max-size=1m", "--log-opt=max-file=1", "--log-opt=compress=false",
                "--tmpfs=/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
                "--tmpfs=/work:rw,nosuid,nodev,size=134217728,mode=0700,uid=65534,gid=65534",
                "--mount", "type=bind,src=" + str(snapshot) + ",dst=/snapshot,readonly",
                "--workdir=/work", "--env=HOME=/tmp", "--env=TMPDIR=/tmp",
                "--env=NODE_ENV=development", "--env=PORT=3000", "--env=HOST=127.0.0.1",
                "--entrypoint=/usr/local/bin/node", image_id, "/opt/olympus-preview/launch.mjs",
                FRAMEWORKS[framework], package_path]
            with self._lock:
                self._pending[handle.name] = handle
            response = self._call(client, *argv)
            if response.returncode or not re.fullmatch(r"[a-f0-9]{64}", response.stdout.strip()):
                raise IsolationUnavailable("preview container creation was not confirmed")
            record = self._inspect(handle)
            if record is None:
                raise IsolationUnavailable("preview container disappeared before start")
            response = self._call(client, "start", handle.name)
            if response.returncode:
                raise IsolationUnavailable("preview container start failed")
            record = self._inspect(handle)
            if record is None or not record["State"]["Running"]:
                raise IsolationUnavailable("preview container is not running")
            handle.status = "container_running"
            return handle
        except BaseException as exc:
            if isinstance(exc, PreviewLifecycleError) and handle is None:
                raise
            if handle:
                self.stop(handle)
                if not handle.cleanup_confirmed:
                    raise PreviewLifecycleError("preview startup failed; cleanup_unconfirmed: " + handle.name, handle) from exc
            if isinstance(exc, (IsolationUnavailable, OSError, subprocess.TimeoutExpired)):
                raise PreviewLifecycleError("preview isolation unavailable: " + type(exc).__name__, handle) from exc
            raise

    def stop(self, handle):
        with self._lock:
            if handle.cleanup_confirmed:
                return True
            if self._pending.get(handle.name) is not handle:
                return False
            try:
                record = self._inspect(handle)
                if record is not None:
                    result = self._call(handle.client, "rm", "--force", handle.name)
                    if result.returncode or self._inspect(handle) is not None:
                        raise IsolationUnavailable("preview removal was not confirmed")
            except BaseException as exc:
                handle.status = "cleanup_unconfirmed"
                self._pending[handle.name] = handle
                if not isinstance(exc, (IsolationUnavailable, OSError, subprocess.TimeoutExpired)):
                    raise
                return False
            try:
                handle.temporary.cleanup()
            except (IsolationUnavailable, OSError):
                handle.status = 'cleanup_unconfirmed'
                return False
            handle.status = "stopped"
            handle.cleanup_confirmed = True
            self._pending.pop(handle.name, None)
            return True

    def pending(self):
        with self._lock:
            return tuple(handle for handle in self._pending.values() if handle.status == "cleanup_unconfirmed")

    def running(self, handle):
        with self._lock:
            if self._pending.get(handle.name) is not handle or handle.status != 'container_running':
                return False
            try:
                record = self._inspect(handle)
                return record is not None and record['State']['Running']
            except (IsolationUnavailable, OSError, subprocess.TimeoutExpired):
                return False

    @staticmethod
    def _request_path(target, query):
        if (not isinstance(target, str) or not target.startswith('/') or target.startswith('//')
                or len(target) > 4096 or not isinstance(query, str) or len(query) > 4096
                or re.search(r'[\x00-\x20\x7f?#]', target) or re.search(r'[\x00-\x20\x7f#]', query)):
            raise IsolationUnavailable('invalid preview request')
        decoded = target
        for _ in range(4):
            if '\\' in decoded or re.search(r'[\x00-\x1f\x7f]', decoded) or '..' in decoded.split('/'):
                raise IsolationUnavailable('invalid preview request')
            if re.search(r'%(?![0-9a-fA-F]{2})', decoded):
                raise IsolationUnavailable('invalid preview path encoding')
            next_value = unquote(decoded, errors='strict')
            if next_value == decoded:
                return
            decoded = next_value
        raise IsolationUnavailable('excessive preview path encoding')

    @staticmethod
    def _capture_http(argv, timeout_seconds=10, output_limit=None, stderr_limit=16000, stderr_tail=True):
        if not 0 < timeout_seconds <= 10:
            raise IsolationUnavailable('invalid preview transport timeout')
        output_limit = MAX_HTTP_ENVELOPE if output_limit is None else output_limit
        if not 0 < output_limit <= MAX_HTTP_ENVELOPE or not 0 < stderr_limit <= MAX_HTTP_ENVELOPE:
            raise IsolationUnavailable('invalid preview transport limit')
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, env=ContainerExecutor._environment())
        stdout, stderr = bytearray(), bytearray()
        overflow, read_failed = Event(), Event()
        def drain(stream, buffer, limit, tail=False):
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    if tail:
                        buffer.extend(chunk); del buffer[:-limit]
                    elif len(buffer) + len(chunk) > limit:
                        overflow.set()
                        process.kill()
                        break
                    else:
                        buffer.extend(chunk)
            except (OSError, ValueError):
                read_failed.set()
            finally:
                stream.close()
        threads = [Thread(target=drain, args=(process.stdout, stdout, output_limit), daemon=True),
            Thread(target=drain, args=(process.stderr, stderr, stderr_limit, stderr_tail), daemon=True)]
        for thread in threads: thread.start()
        try:
            process.wait(timeout=timeout_seconds)
        except BaseException:
            process.kill(); process.wait(timeout=5)
            raise
        finally:
            for thread in threads: thread.join(timeout=5)
        if overflow.is_set() or read_failed.is_set() or any(thread.is_alive() for thread in threads):
            raise IsolationUnavailable('preview transport exceeds limit or is incomplete')
        return subprocess.CompletedProcess(argv, process.returncode, bytes(stdout), bytes(stderr))

    def logs(self, handle):
        """Bounded Docker batch; stdout/stderr of stopped owned containers remain readable."""
        try:
            with self._lock:
                if self._pending.get(handle.name) is not handle or handle.cleanup_confirmed:
                    raise IsolationUnavailable('preview log owner is unavailable')
                if self._inspect(handle) is None:
                    raise IsolationUnavailable('preview log container is absent')
                response = self._capture_http([*handle.client, 'logs', '--timestamps', '--tail=200', handle.name],
                    timeout_seconds=5, output_limit=262144, stderr_limit=262144, stderr_tail=False)
            if response.returncode or len(response.stdout) > 262144 or len(response.stderr) > 262144:
                raise IsolationUnavailable('preview logs are unavailable or exceed limit')
            entries = []
            for stream, data in [('stdout', response.stdout), ('stderr', response.stderr)]:
                lines = data.decode('utf-8', errors='replace').splitlines()
                if len(lines) > 200:
                    raise IsolationUnavailable('preview log count exceeds limit')
                for line in lines:
                    if not line:
                        continue
                    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z) (.*)', line)
                    if not match:
                        raise IsolationUnavailable('invalid preview log timestamp')
                    timestamp, message = match.groups()
                    datetime.fromisoformat(timestamp[:19])
                    entries.append((timestamp, stream, message[:4000]))
            return sorted(entries, key=lambda item: item[0])
        except (IsolationUnavailable, OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise PreviewLifecycleError('preview logs unavailable', handle) from exc

    def fetch(self, handle, target='/', query=''):
        try:
            self._request_path(target, query)
            with self._lock:
                if self._pending.get(handle.name) is not handle or handle.status != 'container_running':
                    raise IsolationUnavailable('preview container is not available')
                record = self._inspect(handle)
                if record is None or not record['State']['Running']:
                    raise IsolationUnavailable('preview container is not running')
                # Fixed image program; no project scripts, host URL, forwarded
                # cookies/authorization, port publishing or shell expansion.
                response = self._capture_http([*handle.client, 'exec', '--user=65534:65534',
                    handle.name, '/usr/local/bin/node', '/opt/olympus-preview/fetch.mjs', target, query])
            if response.returncode or len(response.stdout) > MAX_HTTP_ENVELOPE:
                raise IsolationUnavailable('preview HTTP request failed')
            value = json.loads(response.stdout)
            if (type(value['status']) is not int or not 200 <= value['status'] <= 599
                    or not isinstance(value['content_type'], str) or len(value['content_type']) > 512
                    or re.search(r'[\x00-\x1f\x7f]', value['content_type'])):
                raise ValueError()
            location = value.get('location')
            if location is not None and (not isinstance(location, str) or len(location) > 4096 or re.search(r'[\x00-\x1f\x7f]', location)):
                raise ValueError()
            body = base64.b64decode(value['body'], validate=True)
            if len(body) > MAX_HTTP_BODY:
                raise ValueError()
            headers = {'Content-Type': value['content_type']}
            if location is not None:
                headers['Location'] = location
            return value['status'], headers, body
        except (IsolationUnavailable, OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, binascii.Error) as exc:
            raise PreviewLifecycleError('preview HTTP unavailable', handle) from exc
