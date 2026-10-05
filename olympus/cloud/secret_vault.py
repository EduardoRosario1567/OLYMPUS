from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterable, Iterator, Mapping, Protocol, Tuple, Union
import importlib
import os
import re
import sqlite3
import time

from .deployment import (
    MAX_SECRET_BYTES,
    DeploymentPolicyError,
    SecretReference,
    _environment,
    _safe_id,
    _secret_name,
)


MAX_CIPHERTEXT_BYTES = 128 * 1024


class KeyManagementProvider(Protocol):
    """Adapter implemented by a managed KMS or Secret Manager integration."""

    key_id: str

    def encrypt(self, plaintext: memoryview, context: Mapping[str, str]) -> bytes:
        ...

    def decrypt(self, ciphertext: bytes, context: Mapping[str, str]) -> bytearray:
        ...


class SecretVault(Protocol):
    def put(self, tenant_id: str, project_id: str, environment: str, name: str, value: Union[str, bytes]) -> SecretReference:
        ...

    def list(self, tenant_id: str, project_id: str, environment: str) -> Tuple[SecretReference, ...]:
        ...

    def delete(self, tenant_id: str, project_id: str, environment: str, name: str) -> bool:
        ...

    @contextmanager
    def materialize(self, references: Iterable[SecretReference]) -> Iterator[Mapping[str, memoryview]]:
        ...


def _scope(tenant_id: str, project_id: str, environment: str, name: str) -> Tuple[str, str, str, str]:
    return (
        _safe_id(tenant_id, "tenant_id"),
        _safe_id(project_id, "project_id"),
        _environment(environment),
        _secret_name(name),
    )


def _context(key: Tuple[str, str, str, str], version: int) -> dict[str, str]:
    return {
        "tenant_id": key[0],
        "project_id": key[1],
        "environment": key[2],
        "name": key[3],
        "version": str(version),
        "purpose": "olympus-deployment-secret",
    }


class SQLiteKmsSecretVault:
    """Transactional ciphertext store backed by an injected managed KMS.

    The database never receives plaintext or an encryption key. Associated
    context binds every ciphertext to tenant, project, environment, name and
    version, preventing a stored value from being moved to another scope.
    """

    def __init__(self, path: Union[str, Path], kms: KeyManagementProvider, clock=time.time) -> None:
        key_id = str(getattr(kms, "key_id", "") or "").strip()
        if not key_id or len(key_id) > 512 or any(ord(char) < 32 for char in key_id):
            raise ValueError("invalid KMS key identity")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.kms = kms
        self.key_id = key_id
        self.clock = clock
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS deployment_secrets ("
                "tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, environment TEXT NOT NULL, name TEXT NOT NULL, "
                "version INTEGER NOT NULL, updated_at INTEGER NOT NULL, key_id TEXT NOT NULL, ciphertext BLOB NOT NULL, "
                "PRIMARY KEY(tenant_id,project_id,environment,name))"
            )
        os.chmod(self.path, 0o600)

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _payload(value: Union[str, bytes]) -> bytearray:
        if isinstance(value, str):
            payload = bytearray(value.encode("utf-8"))
        elif isinstance(value, bytes):
            payload = bytearray(value)
        else:
            raise TypeError("secret value must be text or bytes")
        if not payload or len(payload) > MAX_SECRET_BYTES or b"\x00" in payload:
            payload[:] = b"\x00" * len(payload)
            raise ValueError("secret value is empty, invalid or too large")
        return payload

    def put(self, tenant_id: str, project_id: str, environment: str, name: str, value: Union[str, bytes]) -> SecretReference:
        key = _scope(tenant_id, project_id, environment, name)
        plaintext = self._payload(value)
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT version FROM deployment_secrets WHERE tenant_id=? AND project_id=? AND environment=? AND name=?", key
                    ).fetchone()
                    version = int(row[0]) + 1 if row else 1
                    ciphertext = self.kms.encrypt(memoryview(plaintext), _context(key, version))
                    if not isinstance(ciphertext, bytes) or not ciphertext or len(ciphertext) > MAX_CIPHERTEXT_BYTES:
                        raise DeploymentPolicyError("KMS returned invalid ciphertext")
                    updated_at = int(self.clock())
                    connection.execute(
                        "INSERT INTO deployment_secrets(tenant_id,project_id,environment,name,version,updated_at,key_id,ciphertext) "
                        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,project_id,environment,name) DO UPDATE SET "
                        "version=excluded.version,updated_at=excluded.updated_at,key_id=excluded.key_id,ciphertext=excluded.ciphertext",
                        (*key, version, updated_at, self.key_id, sqlite3.Binary(ciphertext)),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return SecretReference(*key, version, updated_at)
        finally:
            plaintext[:] = b"\x00" * len(plaintext)

    def list(self, tenant_id: str, project_id: str, environment: str) -> Tuple[SecretReference, ...]:
        prefix = (_safe_id(tenant_id, "tenant_id"), _safe_id(project_id, "project_id"), _environment(environment))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT name,version,updated_at FROM deployment_secrets WHERE tenant_id=? AND project_id=? AND environment=? ORDER BY name",
                prefix,
            ).fetchall()
        return tuple(SecretReference(*prefix, str(row[0]), int(row[1]), int(row[2])) for row in rows)

    def delete(self, tenant_id: str, project_id: str, environment: str, name: str) -> bool:
        key = _scope(tenant_id, project_id, environment, name)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "DELETE FROM deployment_secrets WHERE tenant_id=? AND project_id=? AND environment=? AND name=?", key
                )
                connection.execute("COMMIT")
                return cursor.rowcount > 0
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @contextmanager
    def materialize(self, references: Iterable[SecretReference]) -> Iterator[Mapping[str, memoryview]]:
        material: dict[str, bytearray] = {}
        try:
            with self._lock, self._connect() as connection:
                for reference in references:
                    key = _scope(reference.tenant_id, reference.project_id, reference.environment, reference.name)
                    row = connection.execute(
                        "SELECT version,key_id,ciphertext FROM deployment_secrets WHERE tenant_id=? AND project_id=? AND environment=? AND name=?", key
                    ).fetchone()
                    if row is None or int(row[0]) != reference.version or str(row[1]) != self.key_id:
                        raise DeploymentPolicyError("secret reference is stale or unavailable")
                    if reference.name in material:
                        raise DeploymentPolicyError("duplicate secret reference")
                    plaintext = self.kms.decrypt(bytes(row[2]), _context(key, reference.version))
                    if not isinstance(plaintext, bytearray) or not plaintext or len(plaintext) > MAX_SECRET_BYTES or b"\x00" in plaintext:
                        if isinstance(plaintext, bytearray):
                            plaintext[:] = b"\x00" * len(plaintext)
                        raise DeploymentPolicyError("KMS returned invalid plaintext")
                    material[reference.name] = plaintext
            yield {name: memoryview(value) for name, value in material.items()}
        finally:
            for value in material.values():
                value[:] = b"\x00" * len(value)

    def rewrap(self, replacement: KeyManagementProvider) -> int:
        replacement_id = str(getattr(replacement, "key_id", "") or "").strip()
        if not replacement_id or replacement_id == self.key_id or len(replacement_id) > 512:
            raise ValueError("replacement KMS key identity is invalid")
        plaintexts: list[bytearray] = []
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    rows = connection.execute(
                        "SELECT tenant_id,project_id,environment,name,version,key_id,ciphertext FROM deployment_secrets ORDER BY tenant_id,project_id,environment,name"
                    ).fetchall()
                    updates = []
                    for row in rows:
                        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
                        version = int(row[4])
                        if str(row[5]) != self.key_id:
                            raise DeploymentPolicyError("secret store contains an unavailable KMS key")
                        plaintext = self.kms.decrypt(bytes(row[6]), _context(key, version))
                        if not isinstance(plaintext, bytearray):
                            raise DeploymentPolicyError("KMS returned invalid plaintext")
                        plaintexts.append(plaintext)
                        ciphertext = replacement.encrypt(memoryview(plaintext), _context(key, version))
                        if not isinstance(ciphertext, bytes) or not ciphertext or len(ciphertext) > MAX_CIPHERTEXT_BYTES:
                            raise DeploymentPolicyError("replacement KMS returned invalid ciphertext")
                        updates.append((replacement_id, sqlite3.Binary(ciphertext), *key))
                    connection.executemany(
                        "UPDATE deployment_secrets SET key_id=?,ciphertext=? WHERE tenant_id=? AND project_id=? AND environment=? AND name=?",
                        updates,
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            self.kms = replacement
            self.key_id = replacement_id
            return len(updates)
        finally:
            for plaintext in plaintexts:
                plaintext[:] = b"\x00" * len(plaintext)


def configured_secret_vault(data_directory: Union[str, Path], provider_spec: str = ""):
    """Compose the safe local vault or an operator-supplied managed KMS adapter.

    The provider factory receives no credentials from Olympus. It must obtain
    them through workload identity or its own managed runtime configuration.
    """
    spec = str(provider_spec or "").strip()
    if not spec:
        from .deployment import MemorySecretVault
        return MemorySecretVault()
    if spec.count(":") != 1:
        raise RuntimeError("OLYMPUS_KMS_PROVIDER must use module:factory")
    module_name, factory_name = spec.split(":", 1)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,255}", module_name) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", factory_name):
        raise RuntimeError("OLYMPUS_KMS_PROVIDER is invalid")
    try:
        factory = getattr(importlib.import_module(module_name), factory_name)
        kms = factory()
    except Exception as exc:
        raise RuntimeError("configured KMS provider could not be initialized") from exc
    return SQLiteKmsSecretVault(Path(data_directory, "deployment-secrets.sqlite3"), kms)
