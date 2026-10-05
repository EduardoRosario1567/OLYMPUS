from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Union
import json
import os
import stat
import tempfile
import zipfile


MANIFEST_NAME = "OLYMPUS-DISTRIBUTION.json"
MAX_BUNDLE_FILES = 500
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_BUNDLE_BYTES = 300 * 1024 * 1024

_PRIVATE_ROOTS = {
    ".git",
    ".github",
    "backend",
    "contexts",
    "docs",
    "frontend",
    "olympus",
    "scripts",
    "tests",
}
_PRIVATE_NAMES = {
    ".env",
    "AGENTS.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-core.txt",
}
_PRIVATE_SUFFIXES = {
    ".c",
    ".cc",
    ".cjs",
    ".cpp",
    ".css.map",
    ".go",
    ".h",
    ".hpp",
    ".js.map",
    ".js",
    ".jsx",
    ".mjs.map",
    ".mjs",
    ".py",
    ".pyc",
    ".pyo",
    ".rs",
    ".ts",
    ".tsx",
}


class BundlePolicyError(ValueError):
    """A public artifact would expose private implementation or unsafe data."""


@dataclass(frozen=True)
class PublicBundleManifest:
    product: str
    version: str
    bundle_type: str
    entrypoint: str
    files: Mapping[str, str]

    def payload(self) -> dict:
        return asdict(self)


def _normalized_name(value: str) -> str:
    raw = value.replace("\\", "/")
    candidate = PurePosixPath(raw)
    if not raw or raw.startswith("/") or ".." in candidate.parts or "." in candidate.parts:
        raise BundlePolicyError("unsafe bundle path: %s" % value)
    if any(not part for part in candidate.parts):
        raise BundlePolicyError("unsafe bundle path: %s" % value)
    return candidate.as_posix()


def _validate_public_name(value: str) -> str:
    name = _normalized_name(value)
    path = PurePosixPath(name)
    lowered = name.lower()
    first = path.parts[0].lower()
    if first in {item.lower() for item in _PRIVATE_ROOTS}:
        raise BundlePolicyError("private product area in public bundle: %s" % name)
    if path.name in _PRIVATE_NAMES or path.name.startswith(".env."):
        raise BundlePolicyError("private configuration in public bundle: %s" % name)
    if any(lowered.endswith(suffix) for suffix in _PRIVATE_SUFFIXES):
        raise BundlePolicyError("source or source-map in public bundle: %s" % name)
    if any(part.startswith(".") for part in path.parts):
        raise BundlePolicyError("hidden path in public bundle: %s" % name)
    return name


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _manifest_bytes(manifest: PublicBundleManifest) -> bytes:
    return (json.dumps(manifest.payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_public_bundle(
    source_root: Union[str, Path],
    target: Union[str, Path],
    *,
    version: str,
    entrypoint: str,
    files: Iterable[str],
) -> PublicBundleManifest:
    """Build a deny-by-default public Runner archive.

    Callers must explicitly enumerate every file. Source code, source maps,
    private product directories, hidden files and symlinks are rejected before
    the target archive is replaced.
    """

    root = Path(source_root).resolve()
    destination = Path(target).resolve()
    if not root.is_dir():
        raise BundlePolicyError("bundle source root does not exist")

    selected: dict[str, Path] = {}
    total = 0
    for value in files:
        name = _validate_public_name(str(value))
        if name == MANIFEST_NAME or name in selected:
            raise BundlePolicyError("duplicate or reserved bundle path: %s" % name)
        source = root.joinpath(*PurePosixPath(name).parts)
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(root)
        except ValueError as exc:
            raise BundlePolicyError("bundle path escapes source root") from exc
        except OSError as exc:
            raise BundlePolicyError("bundle entry does not exist: %s" % name) from exc
        relative_parts = source.relative_to(root).parts
        cursor = root
        has_link = False
        for part in relative_parts:
            cursor = cursor / part
            if cursor.is_symlink():
                has_link = True
                break
        if has_link or not resolved.is_file():
            raise BundlePolicyError("bundle entry must be a regular file: %s" % name)
        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES:
            raise BundlePolicyError("bundle entry exceeds size limit: %s" % name)
        total += size
        if total > MAX_BUNDLE_BYTES:
            raise BundlePolicyError("public bundle exceeds size limit")
        selected[name] = resolved
    if not selected or len(selected) > MAX_BUNDLE_FILES:
        raise BundlePolicyError("invalid public bundle file count")

    safe_entrypoint = _validate_public_name(entrypoint)
    if safe_entrypoint not in selected:
        raise BundlePolicyError("entrypoint is not present in public bundle")

    digests = {name: _digest(path.read_bytes()) for name, path in sorted(selected.items())}
    manifest = PublicBundleManifest("OLYMPUS", version.strip(), "runner", safe_entrypoint, digests)
    if not manifest.version:
        raise BundlePolicyError("bundle version is required")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in sorted(selected.items()):
                archive.write(source, name)
            archive.writestr(MANIFEST_NAME, _manifest_bytes(manifest))
        verify_public_bundle(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def verify_public_bundle(archive_path: Union[str, Path]) -> PublicBundleManifest:
    """Verify paths, content hashes, limits and the public distribution manifest."""

    path = Path(archive_path)
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_BUNDLE_FILES + 1:
                raise BundlePolicyError("public bundle has too many entries")
            by_name: dict[str, zipfile.ZipInfo] = {}
            total = 0
            for entry in entries:
                name = _normalized_name(entry.filename)
                if name in by_name:
                    raise BundlePolicyError("duplicate bundle entry: %s" % name)
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                    raise BundlePolicyError("links and directories are not allowed: %s" % name)
                if entry.file_size > MAX_FILE_BYTES:
                    raise BundlePolicyError("bundle entry exceeds size limit: %s" % name)
                total += entry.file_size
                if total > MAX_BUNDLE_BYTES:
                    raise BundlePolicyError("public bundle exceeds size limit")
                if name != MANIFEST_NAME:
                    _validate_public_name(name)
                by_name[name] = entry
            if MANIFEST_NAME not in by_name:
                raise BundlePolicyError("public distribution manifest is missing")
            try:
                payload = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
                manifest = PublicBundleManifest(
                    product=str(payload["product"]),
                    version=str(payload["version"]),
                    bundle_type=str(payload["bundle_type"]),
                    entrypoint=_validate_public_name(str(payload["entrypoint"])),
                    files={str(key): str(value) for key, value in payload["files"].items()},
                )
            except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
                raise BundlePolicyError("public distribution manifest is invalid") from exc
            if manifest.product != "OLYMPUS" or manifest.bundle_type != "runner" or not manifest.version:
                raise BundlePolicyError("public distribution identity is invalid")
            expected_names = set(by_name) - {MANIFEST_NAME}
            if set(manifest.files) != expected_names or manifest.entrypoint not in expected_names:
                raise BundlePolicyError("public distribution manifest does not match archive")
            for name, expected in manifest.files.items():
                safe_name = _validate_public_name(name)
                if len(expected) != 64 or _digest(archive.read(safe_name)) != expected:
                    raise BundlePolicyError("public bundle integrity check failed: %s" % safe_name)
            return manifest
    except (OSError, zipfile.BadZipFile) as exc:
        raise BundlePolicyError("public bundle is not a readable ZIP archive") from exc
