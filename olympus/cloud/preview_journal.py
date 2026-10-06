"""Private, durable ownership records. No project paths or Docker clients in JSON."""
from pathlib import Path
import fcntl
import json
import os
import re
import stat

from olympus.agent.container_execution import IsolationUnavailable

NAME = re.compile(r"olympus-preview-[a-f0-9]{32}")
IMAGE = re.compile(r"sha256:[a-f0-9]{64}")


class PreviewWorkspace:
    def __init__(self, journal, name):
        self.journal, self.container_name = journal, name
        self.name = str(journal.root / name)

    def cleanup(self):
        self.journal.remove(self.container_name)


class PreviewJournal:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.fd = self.lease = None

    def acquire(self):
        if self.fd is not None:
            return
        current = Path(self.root.anchor)
        for part in self.root.parts[1:]:
            current /= part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            if not stat.S_ISDIR(current.lstat().st_mode):
                raise IsolationUnavailable("linked preview journal directory")
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lease = None
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise IsolationUnavailable("preview journal must be private")
            lease = os.open('.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            self._private_file(lease)
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            if lease is not None:
                os.close(lease)
            os.close(fd)
            raise
        self.fd, self.lease = fd, lease

    @staticmethod
    def _private_file(fd):
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise IsolationUnavailable("unsafe preview ownership record")

    def records(self):
        entries = os.listdir(self.fd)
        if len(entries) > 201:
            raise IsolationUnavailable("preview recovery journal exceeds limit")
        records, directories = {}, set()
        for entry in entries:
            if entry == '.lock':
                continue
            if NAME.fullmatch(entry):
                info = os.stat(entry, dir_fd=self.fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                    raise IsolationUnavailable("unsafe preview workspace")
                directories.add(entry)
                continue
            if not entry.endswith('.json') or not NAME.fullmatch(entry[:-5]):
                raise IsolationUnavailable("unrecognized preview recovery entry")
            fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
            try:
                self._private_file(fd)
                data = os.read(fd, 4097)
                if len(data) > 4096:
                    raise ValueError()
                value = json.loads(data)
                if (set(value) != {'name', 'image_id'} or value['name'] != entry[:-5]
                        or not isinstance(value['image_id'], str) or not IMAGE.fullmatch(value['image_id'])):
                    raise ValueError()
                records[value['name']] = value['image_id']
            except (ValueError, TypeError, KeyError) as exc:
                raise IsolationUnavailable("invalid preview recovery record") from exc
            finally:
                os.close(fd)
        if directories - set(records):
            raise IsolationUnavailable("preview workspace has no ownership record")
        return records

    def create(self, name, image_id):
        if not NAME.fullmatch(name) or not IMAGE.fullmatch(image_id):
            raise IsolationUnavailable("invalid preview registration")
        # O_EXCL plus fsync: no Docker creation before the record is durable.
        fd = os.open(name + '.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            data = json.dumps({'name': name, 'image_id': image_id}).encode()
            if os.write(fd, data) != len(data):
                raise OSError("incomplete preview registration")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        os.mkdir(name, mode=0o700, dir_fd=self.fd)
        os.fsync(self.fd)
        return PreviewWorkspace(self, name)

    @classmethod
    def _remove_tree(cls, parent, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            return
        try:
            for entry in os.listdir(fd):
                info = os.stat(entry, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    cls._remove_tree(fd, entry)
                else:
                    os.unlink(entry, dir_fd=fd)
        finally:
            os.close(fd)
        os.rmdir(name, dir_fd=parent)

    def remove(self, name):
        if self.fd is None or not NAME.fullmatch(name):
            raise IsolationUnavailable("preview journal lease is unavailable")
        self._remove_tree(self.fd, name)
        try:
            os.unlink(name + '.json', dir_fd=self.fd)
        except FileNotFoundError:
            pass
        os.fsync(self.fd)

    def release(self):
        if self.lease is not None:
            os.close(self.lease)
            os.close(self.fd)
            self.fd = self.lease = None
