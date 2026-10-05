from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Dict, Iterable, Iterator, Mapping, Optional, Protocol, Tuple, Union
import json
import os
import re
import stat
import sqlite3
import tempfile
import time
import uuid
import zipfile
from urllib.parse import urlparse


DEPLOYMENT_MANIFEST = "OLYMPUS-DEPLOYMENT.json"
MAX_DEPLOYMENT_FILES = 5000
MAX_DEPLOYMENT_FILE_BYTES = 20 * 1024 * 1024
MAX_DEPLOYMENT_BYTES = 200 * 1024 * 1024
MAX_SECRET_BYTES = 64 * 1024

_ENVIRONMENTS = {"preview", "production"}
_SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PROTECTED_ROOTS = {
    ".executions",
    ".git",
    ".next",
    ".olympus",
    "attachments",
    "coverage",
    "imports",
    "node_modules",
}
_PROTECTED_NAMES = {".DS_Store", ".olympus-attachments.json", DEPLOYMENT_MANIFEST}
_STATIC_ENTRYPOINTS = ("index.html", "app/index.html", "public/index.html", "dist/index.html", "build/index.html")
_PYTHON_ENTRYPOINTS = ("app.py", "main.py", "backend/app.py", "backend/main.py")


class DeploymentPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class SecretReference:
    tenant_id: str
    project_id: str
    environment: str
    name: str
    version: int
    updated_at: int


@dataclass(frozen=True)
class DeploymentArtifact:
    artifact_id: str
    path: str
    sha256: str
    runtime: str
    entrypoint: str
    environment: str
    file_count: int
    size_bytes: int
    secret_names: Tuple[str, ...]


@dataclass(frozen=True)
class DeploymentRequest:
    tenant_id: str
    project_id: str
    version_id: str
    environment: str
    artifact: DeploymentArtifact
    secret_references: Tuple[SecretReference, ...] = ()
    requested_domain: Optional[str] = None
    source_revision: Optional[str] = None


@dataclass(frozen=True)
class ProviderDnsRecord:
    host: str
    value: str
    status: str


@dataclass(frozen=True)
class ProviderDeployment:
    provider: str
    deployment_id: str
    status: str
    url: Optional[str] = None
    provider_reference: Optional[str] = None
    domain_status: Optional[str] = None
    dns_records: Tuple[ProviderDnsRecord, ...] = ()


class DeploymentProvider(Protocol):
    """Replaceable provider boundary; implementations must not retain secrets."""

    provider_id: str

    def deploy(self, request: DeploymentRequest, secrets: Mapping[str, memoryview]) -> ProviderDeployment:
        ...

    def rollback(self, deployment_id: str, target_deployment_id: str) -> ProviderDeployment:
        ...

    def configure_domain(self, deployment_id: str, domain: str) -> ProviderDeployment:
        ...


class DeploymentRecordStore(Protocol):
    def append(self, scope: Tuple[str, str, str], deployment: ProviderDeployment) -> None:
        ...

    def list(self, scope: Tuple[str, str, str]) -> Tuple[ProviderDeployment, ...]:
        ...

    def owns(self, provider: str, deployment_id: str, scope: Tuple[str, str, str]) -> bool:
        ...


class SQLiteDeploymentRecordStore:
    """Append-only deployment audit log with transactional ownership checks."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS deployment_ownership ("
                "provider TEXT NOT NULL, deployment_id TEXT NOT NULL, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, environment TEXT NOT NULL, "
                "PRIMARY KEY(provider,deployment_id));"
                "CREATE TABLE IF NOT EXISTS deployment_events ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, environment TEXT NOT NULL, "
                "provider TEXT NOT NULL, deployment_id TEXT NOT NULL, status TEXT NOT NULL, url TEXT, provider_reference TEXT, "
                "domain_status TEXT, dns_records TEXT NOT NULL, created_at INTEGER NOT NULL);"
                "CREATE INDEX IF NOT EXISTS deployment_scope_idx ON deployment_events(tenant_id,project_id,environment,seq);"
            )
        os.chmod(self.path, 0o600)

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _row(value) -> ProviderDeployment:
        try:
            records = tuple(ProviderDnsRecord(**item) for item in json.loads(value[6]))
            return ProviderDeployment(value[0], value[1], value[2], value[3], value[4], value[5], records)
        except (TypeError, ValueError, KeyError) as exc:
            raise RuntimeError("deployment history is corrupted") from exc

    def append(self, scope: Tuple[str, str, str], deployment: ProviderDeployment) -> None:
        tenant, project, environment = scope
        records = json.dumps([{"host": item.host, "value": item.value, "status": item.status} for item in deployment.dns_records], separators=(",", ":"), sort_keys=True)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT tenant_id,project_id,environment FROM deployment_ownership WHERE provider=? AND deployment_id=?",
                    (deployment.provider, deployment.deployment_id),
                ).fetchone()
                if current is not None and tuple(current) != scope:
                    raise DeploymentPolicyError("deployment identity is already owned by another project")
                connection.execute(
                    "INSERT OR IGNORE INTO deployment_ownership(provider,deployment_id,tenant_id,project_id,environment) VALUES(?,?,?,?,?)",
                    (deployment.provider, deployment.deployment_id, tenant, project, environment),
                )
                connection.execute(
                    "INSERT INTO deployment_events(tenant_id,project_id,environment,provider,deployment_id,status,url,provider_reference,domain_status,dns_records,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (tenant, project, environment, deployment.provider, deployment.deployment_id, deployment.status,
                     deployment.url, deployment.provider_reference, deployment.domain_status, records, int(time.time())),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def list(self, scope: Tuple[str, str, str]) -> Tuple[ProviderDeployment, ...]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT provider,deployment_id,status,url,provider_reference,domain_status,dns_records FROM deployment_events "
                "WHERE tenant_id=? AND project_id=? AND environment=? ORDER BY seq",
                scope,
            ).fetchall()
        return tuple(self._row(row) for row in rows)

    def owns(self, provider: str, deployment_id: str, scope: Tuple[str, str, str]) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT tenant_id,project_id,environment FROM deployment_ownership WHERE provider=? AND deployment_id=?",
                (provider, deployment_id),
            ).fetchone()
        return row is not None and tuple(row) == scope


def _domain(value: str) -> str:
    raw = str(value).strip().rstrip(".")
    if not raw or "://" in raw or any(char in raw for char in "/?#:@") or any(ord(char) <= 32 for char in raw):
        raise ValueError("invalid custom domain")
    try:
        encoded = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("invalid custom domain") from exc
    if len(encoded) > 253 or "." not in encoded:
        raise ValueError("invalid custom domain")
    for label in encoded.split("."):
        if not label or len(label) > 63 or label.startswith("-") or label.endswith("-") or not re.fullmatch(r"[a-z0-9-]+", label):
            raise ValueError("invalid custom domain")
    return encoded


def _safe_id(value: str, label: str) -> str:
    cleaned = str(value).strip()
    if not _SAFE_ID.fullmatch(cleaned):
        raise ValueError("invalid %s" % label)
    return cleaned


def _environment(value: str) -> str:
    cleaned = str(value).strip().lower()
    if cleaned not in _ENVIRONMENTS:
        raise ValueError("environment must be preview or production")
    return cleaned


def _secret_name(value: str) -> str:
    cleaned = str(value).strip()
    if not _SECRET_NAME.fullmatch(cleaned):
        raise ValueError("invalid secret name")
    return cleaned


class MemorySecretVault:
    """Dependency-free session vault for local/beta use.

    It intentionally has no disk persistence. Production must replace it with a
    KMS-backed adapter implementing the same methods.
    """

    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._records: Dict[Tuple[str, str, str, str], Tuple[int, bytearray, int]] = {}
        self._lock = RLock()

    @staticmethod
    def _key(tenant_id: str, project_id: str, environment: str, name: str) -> Tuple[str, str, str, str]:
        return (
            _safe_id(tenant_id, "tenant_id"),
            _safe_id(project_id, "project_id"),
            _environment(environment),
            _secret_name(name),
        )

    def put(self, tenant_id: str, project_id: str, environment: str, name: str, value: Union[str, bytes]) -> SecretReference:
        key = self._key(tenant_id, project_id, environment, name)
        if isinstance(value, str):
            payload = value.encode("utf-8")
        elif isinstance(value, bytes):
            payload = value
        else:
            raise TypeError("secret value must be text or bytes")
        if not payload or len(payload) > MAX_SECRET_BYTES or b"\x00" in payload:
            raise ValueError("secret value is empty, invalid or too large")
        with self._lock:
            previous = self._records.get(key)
            version = (previous[0] + 1) if previous else 1
            if previous:
                previous[1][:] = b"\x00" * len(previous[1])
            updated_at = int(self._clock())
            self._records[key] = (version, bytearray(payload), updated_at)
            return SecretReference(*key, version, updated_at)

    def list(self, tenant_id: str, project_id: str, environment: str) -> Tuple[SecretReference, ...]:
        prefix = (_safe_id(tenant_id, "tenant_id"), _safe_id(project_id, "project_id"), _environment(environment))
        with self._lock:
            refs = [SecretReference(*key, value[0], value[2]) for key, value in self._records.items() if key[:3] == prefix]
        return tuple(sorted(refs, key=lambda item: item.name))

    def delete(self, tenant_id: str, project_id: str, environment: str, name: str) -> bool:
        key = self._key(tenant_id, project_id, environment, name)
        with self._lock:
            previous = self._records.pop(key, None)
            if previous is None:
                return False
            previous[1][:] = b"\x00" * len(previous[1])
            return True

    @contextmanager
    def materialize(self, references: Iterable[SecretReference]) -> Iterator[Mapping[str, memoryview]]:
        material: Dict[str, bytearray] = {}
        try:
            with self._lock:
                for reference in references:
                    key = self._key(reference.tenant_id, reference.project_id, reference.environment, reference.name)
                    stored = self._records.get(key)
                    if stored is None or stored[0] != reference.version:
                        raise DeploymentPolicyError("secret reference is stale or unavailable")
                    if reference.name in material:
                        raise DeploymentPolicyError("duplicate secret reference")
                    material[reference.name] = bytearray(stored[1])
            yield {name: memoryview(value) for name, value in material.items()}
        finally:
            for value in material.values():
                value[:] = b"\x00" * len(value)


class DeploymentCoordinator:
    """Validates ownership and materializes secrets only around provider I/O."""

    def __init__(self, vault, providers: Iterable[DeploymentProvider], record_store: Optional[DeploymentRecordStore] = None) -> None:
        self.vault = vault
        self._providers = {}
        for provider in providers:
            provider_id = _safe_id(provider.provider_id, "provider_id")
            if provider_id in self._providers:
                raise ValueError("duplicate deployment provider")
            self._providers[provider_id] = provider
        self._records: Dict[Tuple[str, str, str], list] = {}
        self._ownership: Dict[Tuple[str, str], Tuple[str, str, str]] = {}
        self._lock = RLock()
        self._record_store = record_store

    def _remember(self, scope: Tuple[str, str, str], result: ProviderDeployment) -> None:
        if self._record_store is not None:
            self._record_store.append(scope, result)
        self._records.setdefault(scope, []).append(result)
        self._ownership[(result.provider, result.deployment_id)] = scope

    def _owns(self, provider: str, deployment_id: str, scope: Tuple[str, str, str]) -> bool:
        if self._ownership.get((provider, deployment_id)) == scope:
            return True
        return self._record_store is not None and self._record_store.owns(provider, deployment_id, scope)

    @staticmethod
    def _scope(request: DeploymentRequest) -> Tuple[str, str, str]:
        return (
            _safe_id(request.tenant_id, "tenant_id"),
            _safe_id(request.project_id, "project_id"),
            _environment(request.environment),
        )

    @staticmethod
    def _validate_provider_result(provider_id: str, value: ProviderDeployment) -> ProviderDeployment:
        if value.provider != provider_id:
            raise DeploymentPolicyError("deployment provider returned an invalid identity")
        _safe_id(value.deployment_id, "deployment_id")
        if value.status not in {"queued", "building", "ready", "failed"}:
            raise DeploymentPolicyError("deployment provider returned an invalid status")
        if value.url is not None:
            parsed = urlparse(value.url)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise DeploymentPolicyError("deployment provider returned an unsafe URL")
        if value.domain_status is not None and value.domain_status not in {"pending", "configured", "failed"}:
            raise DeploymentPolicyError("deployment provider returned an invalid domain status")
        for record in value.dns_records:
            if not isinstance(record, ProviderDnsRecord):
                raise DeploymentPolicyError("deployment provider returned invalid DNS instructions")
            if not record.host or len(record.host) > 253 or not record.value or len(record.value) > 2048:
                raise DeploymentPolicyError("deployment provider returned invalid DNS instructions")
            if any(ord(char) < 32 for char in record.host + record.value + record.status):
                raise DeploymentPolicyError("deployment provider returned invalid DNS instructions")
        return value

    def deploy(self, provider_id: str, request: DeploymentRequest) -> ProviderDeployment:
        selected_provider = _safe_id(provider_id, "provider_id")
        provider = self._providers.get(selected_provider)
        if provider is None:
            raise DeploymentPolicyError("deployment provider is unavailable")
        scope = self._scope(request)
        _safe_id(request.version_id, "version_id")
        if request.artifact.environment != scope[2]:
            raise DeploymentPolicyError("artifact belongs to another environment")
        artifact_path = Path(request.artifact.path)
        try:
            artifact_valid = artifact_path.is_file() and _digest(artifact_path) == request.artifact.sha256
        except OSError:
            artifact_valid = False
        if not artifact_valid:
            raise DeploymentPolicyError("deployment artifact integrity check failed")
        verified = verify_deployment_artifact(artifact_path)
        if (
            _safe_id(verified["artifact_id"], "artifact_id") != request.artifact.artifact_id
            or verified["runtime"] != request.artifact.runtime
            or verified["entrypoint"] != request.artifact.entrypoint
            or verified["environment"] != request.artifact.environment
            or tuple(sorted(verified.get("secret_names", []))) != request.artifact.secret_names
            or len(verified["files"]) != request.artifact.file_count
            or sum(item["size"] for item in verified["files"].values()) != request.artifact.size_bytes
        ):
            raise DeploymentPolicyError("deployment artifact metadata does not match")
        references = tuple(request.secret_references)
        if tuple(sorted(item.name for item in references)) != request.artifact.secret_names:
            raise DeploymentPolicyError("deployment secret references do not match artifact")
        for reference in references:
            if (reference.tenant_id, reference.project_id, reference.environment) != scope:
                raise DeploymentPolicyError("secret reference belongs to another scope")
        if request.requested_domain is not None:
            _domain(request.requested_domain)
        try:
            with self.vault.materialize(references) as material:
                result = provider.deploy(request, material)
        except DeploymentPolicyError:
            raise
        except Exception as exc:
            raise DeploymentPolicyError("deployment provider failed safely") from exc
        result = self._validate_provider_result(selected_provider, result)
        with self._lock:
            self._remember(scope, result)
        return result

    def list(self, tenant_id: str, project_id: str, environment: str) -> Tuple[ProviderDeployment, ...]:
        scope = (_safe_id(tenant_id, "tenant_id"), _safe_id(project_id, "project_id"), _environment(environment))
        with self._lock:
            if self._record_store is not None:
                values = self._record_store.list(scope)
                for item in values:
                    if item.provider not in self._providers:
                        raise DeploymentPolicyError("deployment history contains an unavailable provider")
                return tuple(self._validate_provider_result(item.provider, item) for item in values)
            return tuple(self._records.get(scope, ()))

    def rollback(
        self,
        tenant_id: str,
        project_id: str,
        environment: str,
        provider_id: str,
        deployment_id: str,
        target_deployment_id: str,
    ) -> ProviderDeployment:
        scope = (_safe_id(tenant_id, "tenant_id"), _safe_id(project_id, "project_id"), _environment(environment))
        selected_provider = _safe_id(provider_id, "provider_id")
        provider = self._providers.get(selected_provider)
        if provider is None:
            raise DeploymentPolicyError("deployment provider is unavailable")
        with self._lock:
            if not self._owns(selected_provider, deployment_id, scope) or not self._owns(selected_provider, target_deployment_id, scope):
                raise DeploymentPolicyError("deployment does not belong to this project")
        try:
            result = provider.rollback(deployment_id, target_deployment_id)
        except Exception as exc:
            raise DeploymentPolicyError("deployment provider failed safely") from exc
        result = self._validate_provider_result(selected_provider, result)
        with self._lock:
            self._remember(scope, result)
        return result

    def configure_domain(
        self,
        tenant_id: str,
        project_id: str,
        environment: str,
        provider_id: str,
        deployment_id: str,
        domain: str,
    ) -> ProviderDeployment:
        scope = (_safe_id(tenant_id, "tenant_id"), _safe_id(project_id, "project_id"), _environment(environment))
        selected_provider = _safe_id(provider_id, "provider_id")
        provider = self._providers.get(selected_provider)
        if provider is None:
            raise DeploymentPolicyError("deployment provider is unavailable")
        normalized = _domain(domain)
        with self._lock:
            if not self._owns(selected_provider, deployment_id, scope):
                raise DeploymentPolicyError("deployment does not belong to this project")
        try:
            result = provider.configure_domain(deployment_id, normalized)
        except Exception as exc:
            raise DeploymentPolicyError("deployment provider failed safely") from exc
        result = self._validate_provider_result(selected_provider, result)
        with self._lock:
            self._remember(scope, result)
        return result


def _is_protected(relative: Path) -> bool:
    if not relative.parts:
        return True
    if relative.parts[0] in _PROTECTED_ROOTS or relative.name in _PROTECTED_NAMES:
        return True
    return any(part.startswith(".") or part == ".env" or part.startswith(".env.") for part in relative.parts)


def _digest(path: Path) -> str:
    result = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _runtime(root: Path, names: set) -> Tuple[str, str]:
    if "Dockerfile" in names:
        return "container", "Dockerfile"
    if "package.json" in names:
        return "node", "package.json"
    for entrypoint in _PYTHON_ENTRYPOINTS:
        if entrypoint in names and ("requirements.txt" in names or "pyproject.toml" in names):
            return "python", entrypoint
    for entrypoint in _STATIC_ENTRYPOINTS:
        if entrypoint in names:
            return "static", entrypoint
    raise DeploymentPolicyError("project does not contain a supported deployment entrypoint")


def build_deployment_artifact(
    source_root: Union[str, Path],
    target: Union[str, Path],
    *,
    environment: str,
    secret_references: Iterable[SecretReference] = (),
) -> DeploymentArtifact:
    root = Path(source_root).resolve()
    destination = Path(target).resolve()
    env = _environment(environment)
    if not root.is_dir():
        raise DeploymentPolicyError("project source root does not exist")

    refs = tuple(secret_references)
    secret_names = tuple(sorted({_secret_name(item.name) for item in refs}))
    if len(secret_names) != len(refs):
        raise DeploymentPolicyError("duplicate secret reference")
    for reference in refs:
        if reference.environment != env:
            raise DeploymentPolicyError("secret belongs to another environment")

    selected = []
    inventory = {}
    total = 0
    for source in sorted(root.rglob("*")):
        relative = source.relative_to(root)
        if _is_protected(relative):
            continue
        if source.is_symlink():
            raise DeploymentPolicyError("project contains a symbolic link that cannot be deployed safely")
        if not source.is_file():
            continue
        size = source.stat().st_size
        if size > MAX_DEPLOYMENT_FILE_BYTES:
            raise DeploymentPolicyError("deployment file exceeds the safe size limit")
        total += size
        if len(selected) >= MAX_DEPLOYMENT_FILES or total > MAX_DEPLOYMENT_BYTES:
            raise DeploymentPolicyError("project exceeds deployment limits")
        name = relative.as_posix()
        selected.append((source, name))
        inventory[name] = {"sha256": _digest(source), "size": size}

    runtime, entrypoint = _runtime(root, set(inventory))
    artifact_id = uuid.uuid4().hex[:20]
    manifest = {
        "artifact_id": artifact_id,
        "environment": env,
        "entrypoint": entrypoint,
        "files": inventory,
        "format": 1,
        "runtime": runtime,
        "secret_names": list(secret_names),
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source, name in selected:
                archive.write(source, name)
            archive.writestr(DEPLOYMENT_MANIFEST, manifest_bytes)
        verified = verify_deployment_artifact(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return DeploymentArtifact(
        artifact_id,
        str(destination),
        _digest(destination),
        verified["runtime"],
        verified["entrypoint"],
        verified["environment"],
        len(inventory),
        total,
        secret_names,
    )


def verify_deployment_artifact(archive_path: Union[str, Path]) -> dict:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DEPLOYMENT_FILES + 1:
                raise DeploymentPolicyError("deployment archive contains too many entries")
            names = set()
            total = 0
            for entry in entries:
                raw = entry.filename.replace("\\", "/")
                relative = PurePosixPath(raw)
                if not raw or raw.startswith("/") or ".." in relative.parts or raw in names:
                    raise DeploymentPolicyError("deployment archive contains an unsafe path")
                names.add(raw)
                if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):
                    raise DeploymentPolicyError("deployment archive contains a link or directory entry")
                if raw != DEPLOYMENT_MANIFEST and _is_protected(Path(*relative.parts)):
                    raise DeploymentPolicyError("deployment archive contains a protected file")
                if entry.file_size > MAX_DEPLOYMENT_FILE_BYTES:
                    raise DeploymentPolicyError("deployment file exceeds the safe size limit")
                total += entry.file_size
                if total > MAX_DEPLOYMENT_BYTES:
                    raise DeploymentPolicyError("deployment archive exceeds the safe size limit")
            if DEPLOYMENT_MANIFEST not in names:
                raise DeploymentPolicyError("deployment manifest is missing")
            try:
                manifest = json.loads(archive.read(DEPLOYMENT_MANIFEST).decode("utf-8"))
                if manifest.get("format") != 1:
                    raise DeploymentPolicyError("deployment manifest version is unsupported")
                env = _environment(manifest["environment"])
                runtime = str(manifest["runtime"])
                entrypoint = str(manifest["entrypoint"])
                secret_names = [_secret_name(value) for value in manifest.get("secret_names", [])]
                inventory = manifest["files"]
                if runtime not in {"container", "node", "python", "static"} or not isinstance(inventory, dict):
                    raise DeploymentPolicyError("deployment manifest is invalid")
                if set(inventory) != names - {DEPLOYMENT_MANIFEST} or entrypoint not in inventory:
                    raise DeploymentPolicyError("deployment manifest does not match archive")
                if len(secret_names) != len(set(secret_names)):
                    raise DeploymentPolicyError("deployment manifest contains duplicate secrets")
                for name, metadata in inventory.items():
                    if _is_protected(Path(*PurePosixPath(name).parts)):
                        raise DeploymentPolicyError("deployment manifest contains a protected file")
                    payload = archive.read(name)
                    if not isinstance(metadata, dict) or metadata.get("size") != len(payload) or metadata.get("sha256") != sha256(payload).hexdigest():
                        raise DeploymentPolicyError("deployment artifact integrity check failed")
                manifest["environment"] = env
                return manifest
            except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DeploymentPolicyError("deployment manifest is invalid") from exc
    except (OSError, zipfile.BadZipFile) as exc:
        raise DeploymentPolicyError("deployment artifact is not a readable ZIP") from exc
