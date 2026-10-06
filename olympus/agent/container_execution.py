"""Fail-closed execution of project tests in an already provisioned local Docker.

No package/image installation, remote daemon, host workspace mount, or host
fallback. Docker contracts are not evidence of OS isolation: run the real gate
on the supported runtime before releasing this candidate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from threading import Thread
import uuid

RUNNER_IMAGE = 'olympus-project-runner:3.0.8-candidate'
RUNNER_LABEL = 'org.olympus.project-runner'
EXCLUDED_DIRS = frozenset({'.git', '.olympus', '.venv', 'venv', 'node_modules',
    '__pycache__', '.pytest_cache', 'attachments', 'imports'})
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 1000


class IsolationUnavailable(ValueError):
    pass


def _excluded(name):
    lower = name.lower()
    return (lower.startswith('.env') or lower in {'credentials', 'credentials.json',
        'secrets.json', 'secrets.yaml', 'secrets.yml', 'id_rsa', 'id_ed25519'}
        or lower.endswith(('.pem', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3', '.db')))


def snapshot_project(root, destination):
    """Copy regular files through no-follow descriptors; refuse every symlink.

    The real project is never mounted. Tests cannot change a reviewed delivery.
    Known credential/state files are excluded; business code itself is trusted
    by its owner to contain only data the test is allowed to read.
    """
    root = Path(root).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination == root or root in destination.parents:
        raise IsolationUnavailable('snapshot destination must be outside project')
    descriptor = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    count = total = 0
    try:
        for relative, directories, files, directory_fd in os.fwalk('.', dir_fd=descriptor,
                follow_symlinks=False):
            for name in list(directories):
                if stat.S_ISLNK(os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode):
                    raise IsolationUnavailable('linked project directory refused')
                if name in EXCLUDED_DIRS or _excluded(name):
                    directories.remove(name)
            target = destination / relative
            target.mkdir(parents=True, exist_ok=True)
            target.chmod(0o755)
            for name in files:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise IsolationUnavailable('nonregular project resource refused')
                if _excluded(name):
                    continue
                count += 1
                if count > MAX_FILES or info.st_size > MAX_FILE:
                    raise IsolationUnavailable('project snapshot exceeds limit')
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                with os.fdopen(fd, 'rb') as stream:
                    current = os.fstat(stream.fileno())
                    if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                        raise IsolationUnavailable('project resource changed while copying')
                    data = stream.read(MAX_FILE + 1)
                total += len(data)
                if len(data) > MAX_FILE or total > MAX_TOTAL:
                    raise IsolationUnavailable('project snapshot exceeds limit')
                output = target / name
                output.write_bytes(data)
                output.chmod(0o644)
    finally:
        os.close(descriptor)
    return {'files': count, 'bytes': total}


class ContainerExecutor:
    def __init__(self, image=RUNNER_IMAGE):
        self.image = image

    @staticmethod
    def _client():
        docker = shutil.which('docker')
        if not docker:
            raise IsolationUnavailable('local Docker CLI is unavailable')
        sockets = (Path('/var/run/docker.sock'), Path.home() / '.docker/run/docker.sock')
        for path in sockets:
            try:
                if stat.S_ISSOCK(path.stat().st_mode):
                    return (docker, '--host', 'unix://' + str(path))
            except OSError:
                pass
        raise IsolationUnavailable('local Docker socket is unavailable')

    @staticmethod
    def _environment():
        # Docker client only. Container env is explicitly enumerated in argv.
        return {'PATH': os.defpath, 'HOME': '/nonexistent', 'LANG': 'C.UTF-8'}

    def _image_id(self, client):
        try:
            result = subprocess.run([*client, 'image', 'inspect', self.image],
                capture_output=True, text=True, timeout=10, env=self._environment(), shell=False)
        except subprocess.TimeoutExpired:
            raise IsolationUnavailable('local Docker image inspection exceeded deadline')
        if result.returncode:
            raise IsolationUnavailable('approved runner image is not installed locally')
        try:
            records = json.loads(result.stdout)
            if len(records) != 1:
                raise ValueError()
            record = records[0]
            image_id = record['Id']
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
                raise ValueError()
            if record.get('Config', {}).get('Labels', {}).get(RUNNER_LABEL) != 'v1':
                raise ValueError()
            return image_id
        except (ValueError, TypeError, KeyError, AttributeError):
            raise IsolationUnavailable('runner image identity or role is invalid')

    @staticmethod
    def _command(command):
        command = tuple(command)
        if not command or not all(isinstance(arg, str) and '\x00' not in arg for arg in command):
            raise IsolationUnavailable('invalid project command')
        executable = command[0]
        if executable == sys.executable or executable in {'python', 'python3'}:
            executable = 'python3'
        elif executable not in {'zsh'}:
            raise IsolationUnavailable('project test executable is not supported')
        return (executable, *command[1:])

    def run(self, root, command, timeout_seconds):
        command = tuple(command)
        client = None
        name = 'olympus-test-' + uuid.uuid4().hex
        attempted = False
        result = None
        try:
            if not 0 < timeout_seconds <= 300:
                raise IsolationUnavailable('invalid test timeout')
            translated = self._command(command)
            client = self._client()
            image_id = self._image_id(client)
            with tempfile.TemporaryDirectory(prefix='olympus-container-') as temporary:
                project = Path(temporary) / 'project'
                snapshot_project(root, project)
                argv = [*client, 'run', '--rm', '--pull=never', '--name', name,
                    '--log-driver=none',
                    '--label', RUNNER_LABEL + '=v1', '--network=none', '--read-only',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                    '--user=65534:65534', '--pids-limit=128', '--memory=512m',
                    '--memory-swap=512m', '--cpus=1', '--ulimit=nofile=256:256',
                    '--tmpfs=/tmp:rw,nosuid,nodev,size=67108864,mode=1777',
                    '--mount', 'type=bind,src=' + str(project) + ',dst=/workspace,readonly',
                    '--workdir=/workspace', '--env=HOME=/tmp', '--env=TMPDIR=/tmp',
                    '--env=PYTHONPATH=/workspace', '--env=PYTHONNOUSERSITE=1',
                    '--env=PYTHONDONTWRITEBYTECODE=1', '--env=PYTHONIOENCODING=utf-8',
                    '--entrypoint', translated[0], image_id, *translated[1:]]
                attempted = True
                process = self._capture(argv, timeout_seconds)
                result = subprocess.CompletedProcess(command, process.returncode, process.stdout, process.stderr)
                result.execution_started = process.returncode != 125
                return result
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(command, 124, '', 'isolated test exceeded deadline')
            return result
        except (IsolationUnavailable, OSError) as exc:
            result = subprocess.CompletedProcess(command, 125, '', 'execution_isolation_unavailable: ' + str(exc))
            return result
        finally:
            if attempted and client:
                try:
                    cleanup = subprocess.run([*client, 'rm', '--force', name], capture_output=True,
                        text=True, timeout=10, env=self._environment(), shell=False)
                    # --rm may already have removed this exact container.
                    absent = cleanup.returncode == 1 and bool(re.search(
                        r'No such container:\s*' + re.escape(name) + r'\s*$', cleanup.stderr or ''))
                    if cleanup.returncode != 0 and not absent:
                        raise IsolationUnavailable('container removal could not be confirmed')
                except (IsolationUnavailable, OSError, subprocess.TimeoutExpired):
                    if result is not None:
                        result.stderr = (result.stderr or '') + '\nexecution_cleanup_unconfirmed: ' + name
                        if result.returncode == 0:
                            result.returncode = 125

    def _capture(self, argv, timeout):
        """Drain both streams continuously, retaining at most 16 KiB each."""
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self._environment(), shell=False)
        buffers = [bytearray(), bytearray()]
        def drain(stream, buffer):
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    del buffer[:-16000]
            finally:
                stream.close()
        threads = [Thread(target=drain, args=(stream, buffer), daemon=True)
            for stream, buffer in zip((process.stdout, process.stderr), buffers)]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise
        finally:
            for thread in threads:
                thread.join(timeout=5)
        return subprocess.CompletedProcess(argv, process.returncode,
            *(buffer.decode('utf-8', errors='replace') for buffer in buffers))
