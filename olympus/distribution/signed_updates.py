from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Optional, Tuple, Union
from urllib.parse import urlparse
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time

from .public_bundle import MAX_BUNDLE_BYTES, PublicBundleManifest, verify_public_bundle


MAX_RELEASE_MANIFEST_BYTES = 64 * 1024
MAX_RELEASE_SIGNATURE_BYTES = 64 * 1024
_PLATFORMS = {"linux", "macos", "windows"}
_ARCHITECTURES = {"x86_64", "arm64"}
_CHANNELS = {"stable", "beta"}
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9][A-Za-z0-9.-]{0,63}))?$")


class RunnerUpdateError(ValueError):
    pass


@dataclass(frozen=True)
class RunnerReleaseManifest:
    format_version: int
    product: str
    version: str
    minimum_version: str
    channel: str
    platform: str
    architecture: str
    artifact_url: str
    artifact_sha256: str
    artifact_size: int
    released_at: int

    def payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VerifiedRunnerUpdate:
    release: RunnerReleaseManifest
    bundle: PublicBundleManifest
    artifact_path: str
    canonical_manifest: bytes = field(repr=False)
    signature: bytes = field(repr=False)


class RunnerReleaseCatalog:
    """Read-only signed release catalog populated by the private CI pipeline."""

    def __init__(self, directory: Union[str, Path], public_key: Union[str, Path]) -> None:
        raw = Path(directory)
        if raw.is_symlink():
            raise RunnerUpdateError("Runner release directory is unsafe")
        self.directory = raw.resolve()
        if not self.directory.is_dir():
            raise RunnerUpdateError("Runner release directory is unavailable")
        self.public_key = _key(public_key, False)

    def latest(self, *, platform: str, architecture: str, channel: str, current_version: str,
               now: Optional[int] = None) -> VerifiedRunnerUpdate:
        platform_value = str(platform).strip().lower()
        architecture_value = str(architecture).strip().lower()
        channel_value = str(channel).strip().lower()
        if platform_value not in _PLATFORMS or architecture_value not in _ARCHITECTURES or channel_value not in _CHANNELS:
            raise RunnerUpdateError("invalid Runner release target")
        basename = "%s-%s-%s" % (platform_value, architecture_value, channel_value)
        return verify_signed_release(
            self.directory / (basename + ".json"),
            self.directory / (basename + ".sig"),
            self.directory / (basename + ".zip"),
            public_key=self.public_key,
            expected_platform=platform_value,
            expected_architecture=architecture_value,
            expected_channel=channel_value,
            current_version=current_version,
            now=now,
        )


def _version(value: str) -> Tuple[int, int, int, int, str]:
    match = _VERSION.fullmatch(str(value or "").strip())
    if not match:
        raise RunnerUpdateError("invalid Runner version")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4) or ""
    return major, minor, patch, 0 if prerelease else 1, prerelease


def _https_url(value: str) -> str:
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise RunnerUpdateError("Runner artifact URL must use HTTPS")
    if len(clean) > 2048 or any(ord(char) < 32 for char in clean):
        raise RunnerUpdateError("invalid Runner artifact URL")
    return clean


def _digest(path: Path) -> str:
    result = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _canonical(manifest: RunnerReleaseManifest) -> bytes:
    return (json.dumps(manifest.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _key(path: Union[str, Path], private: bool) -> Path:
    raw = Path(path)
    if raw.is_symlink():
        raise RunnerUpdateError("signing key is unavailable or unsafe")
    value = raw.resolve()
    if not value.is_file() or value.stat().st_size > 64 * 1024:
        raise RunnerUpdateError("signing key is unavailable or unsafe")
    if private and stat.S_IMODE(value.stat().st_mode) & 0o077:
        raise RunnerUpdateError("private signing key permissions must be 0600 or stricter")
    return value


def _openssl(arguments: list[str]) -> None:
    try:
        result = subprocess.run(
            ["openssl", *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerUpdateError("OpenSSL signing service is unavailable") from exc
    if result.returncode != 0:
        raise RunnerUpdateError("Runner release signature is invalid")


def create_signed_release(
    artifact_path: Union[str, Path],
    manifest_path: Union[str, Path],
    signature_path: Union[str, Path],
    *,
    private_key: Union[str, Path],
    public_key: Union[str, Path],
    version: str,
    minimum_version: str,
    channel: str,
    platform: str,
    architecture: str,
    artifact_url: str,
    released_at: Optional[int] = None,
) -> RunnerReleaseManifest:
    artifact_input = Path(artifact_path)
    artifact = artifact_input.resolve()
    if artifact_input.is_symlink() or not artifact.is_file() or artifact.stat().st_size > MAX_BUNDLE_BYTES:
        raise RunnerUpdateError("Runner artifact is unavailable or too large")
    bundle = verify_public_bundle(artifact)
    release_version = str(version).strip()
    minimum = str(minimum_version).strip()
    release_key = _version(release_version)
    minimum_key = _version(minimum)
    if minimum_key > release_key:
        raise RunnerUpdateError("minimum Runner version cannot exceed release version")
    if bundle.version != release_version:
        raise RunnerUpdateError("release and Runner bundle versions do not match")
    channel_value = str(channel).strip().lower()
    platform_value = str(platform).strip().lower()
    architecture_value = str(architecture).strip().lower()
    if channel_value not in _CHANNELS or platform_value not in _PLATFORMS or architecture_value not in _ARCHITECTURES:
        raise RunnerUpdateError("invalid Runner release target")
    manifest = RunnerReleaseManifest(
        1, "OLYMPUS-RUNNER", release_version, minimum, channel_value, platform_value,
        architecture_value, _https_url(artifact_url), _digest(artifact), artifact.stat().st_size,
        int(time.time() if released_at is None else released_at),
    )
    payload = _canonical(manifest)
    if len(payload) > MAX_RELEASE_MANIFEST_BYTES:
        raise RunnerUpdateError("Runner release manifest is too large")
    destination = Path(manifest_path).resolve()
    signature_destination = Path(signature_path).resolve()
    if destination == signature_destination:
        raise RunnerUpdateError("manifest and signature paths must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    signature_destination.parent.mkdir(parents=True, exist_ok=True)
    private = _key(private_key, True)
    public = _key(public_key, False)
    manifest_fd, manifest_temp_name = tempfile.mkstemp(prefix=destination.name + ".", dir=str(destination.parent))
    signature_fd, signature_temp_name = tempfile.mkstemp(prefix=signature_destination.name + ".", dir=str(signature_destination.parent))
    os.close(signature_fd)
    manifest_temp = Path(manifest_temp_name)
    signature_temp = Path(signature_temp_name)
    try:
        with os.fdopen(manifest_fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _openssl(["dgst", "-sha256", "-sign", str(private), "-out", str(signature_temp), str(manifest_temp)])
        if not signature_temp.is_file() or not 0 < signature_temp.stat().st_size <= MAX_RELEASE_SIGNATURE_BYTES:
            raise RunnerUpdateError("Runner release signature is invalid")
        _openssl(["dgst", "-sha256", "-verify", str(public), "-signature", str(signature_temp), str(manifest_temp)])
        os.chmod(manifest_temp, 0o644)
        os.chmod(signature_temp, 0o644)
        manifest_temp.replace(destination)
        signature_temp.replace(signature_destination)
    finally:
        manifest_temp.unlink(missing_ok=True)
        signature_temp.unlink(missing_ok=True)
    return manifest


def verify_signed_release(
    manifest_path: Union[str, Path],
    signature_path: Union[str, Path],
    artifact_path: Union[str, Path],
    *,
    public_key: Union[str, Path],
    expected_platform: str,
    expected_architecture: str,
    expected_channel: str = "stable",
    current_version: Optional[str] = None,
    now: Optional[int] = None,
) -> VerifiedRunnerUpdate:
    manifest_input = Path(manifest_path)
    signature_input = Path(signature_path)
    artifact_input = Path(artifact_path)
    manifest_file = manifest_input.resolve()
    signature_file = signature_input.resolve()
    artifact = artifact_input.resolve()
    for raw, path, maximum in ((manifest_input, manifest_file, MAX_RELEASE_MANIFEST_BYTES), (signature_input, signature_file, MAX_RELEASE_SIGNATURE_BYTES)):
        if raw.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
            raise RunnerUpdateError("Runner release metadata is unavailable or unsafe")
    public = _key(public_key, False)
    manifest_bytes = manifest_file.read_bytes()
    signature_bytes = signature_file.read_bytes()
    with tempfile.TemporaryDirectory(prefix="olympus-release-verify-") as verification_directory:
        verified_manifest_path = Path(verification_directory, "release.json")
        verified_signature_path = Path(verification_directory, "release.sig")
        verified_manifest_path.write_bytes(manifest_bytes)
        verified_signature_path.write_bytes(signature_bytes)
        _openssl(["dgst", "-sha256", "-verify", str(public), "-signature", str(verified_signature_path), str(verified_manifest_path)])
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
        manifest = RunnerReleaseManifest(**payload)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise RunnerUpdateError("Runner release manifest is invalid") from exc
    if _canonical(manifest) != manifest_bytes:
        raise RunnerUpdateError("Runner release manifest is not canonical")
    if manifest.format_version != 1 or manifest.product != "OLYMPUS-RUNNER":
        raise RunnerUpdateError("Runner release identity is invalid")
    release_key = _version(manifest.version)
    minimum_key = _version(manifest.minimum_version)
    if manifest.platform != expected_platform or manifest.architecture != expected_architecture or manifest.channel != expected_channel:
        raise RunnerUpdateError("Runner release target does not match this installation")
    _https_url(manifest.artifact_url)
    current_key = _version(current_version) if current_version is not None else None
    if current_key is not None and release_key <= current_key:
        raise RunnerUpdateError("Runner update is not newer than the installed version")
    if current_key is not None and current_key < minimum_key:
        raise RunnerUpdateError("Runner installation is too old for this incremental update")
    timestamp = int(time.time() if now is None else now)
    if manifest.released_at <= 0 or manifest.released_at > timestamp + 300:
        raise RunnerUpdateError("Runner release timestamp is invalid")
    if artifact_input.is_symlink() or not artifact.is_file() or artifact.stat().st_size != manifest.artifact_size:
        raise RunnerUpdateError("Runner update artifact size does not match")
    if _digest(artifact) != manifest.artifact_sha256:
        raise RunnerUpdateError("Runner update artifact integrity check failed")
    bundle = verify_public_bundle(artifact)
    if bundle.version != manifest.version:
        raise RunnerUpdateError("Runner update bundle version does not match")
    return VerifiedRunnerUpdate(manifest, bundle, str(artifact), manifest_bytes, signature_bytes)


def stage_runner_update(verified: VerifiedRunnerUpdate, destination_directory: Union[str, Path]) -> Path:
    raw_destination = Path(destination_directory)
    if raw_destination.is_symlink():
        raise RunnerUpdateError("Runner update destination is unsafe")
    destination_root = raw_destination.resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / ("olympus-runner-%s.zip" % verified.release.version)
    descriptor, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", dir=str(destination_root))
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with Path(verified.artifact_path).open("rb") as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        if _digest(temporary) != verified.release.artifact_sha256:
            raise RunnerUpdateError("staged Runner update failed integrity verification")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
