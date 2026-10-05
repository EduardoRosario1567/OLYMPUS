from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import asdict, dataclass, field
from pathlib import Path
from hashlib import sha256
from threading import Lock
from typing import Callable, Dict, List, Optional, Protocol, Tuple
import hmac
import json
import os
import re
import secrets
import sqlite3
import time


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_PLATFORMS = {"linux", "macos", "windows"}
_TOKEN_PREFIX = "olr1"
_MAX_TOKEN_BYTES = 4096
_MAX_STATE_BYTES = 16 * 1024 * 1024
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class AccessDenied(ValueError):
    """Runner enrollment or credential is invalid, expired or revoked."""


@dataclass(frozen=True)
class EnrollmentTicket:
    code: str = field(repr=False)
    expires_at: int


@dataclass(frozen=True)
class RunnerCredential:
    installation_id: str
    refresh_token: str = field(repr=False)
    access_token: str = field(repr=False)
    access_expires_at: int


@dataclass(frozen=True)
class RunnerClaims:
    tenant_id: str
    installation_id: str
    license_id: str
    issued_at: int
    expires_at: int
    token_id: str


@dataclass(frozen=True)
class RunnerInstallation:
    tenant_id: str
    installation_id: str
    license_id: str
    platform: str
    runner_version: str
    created_at: int
    last_seen_at: int
    license_expires_at: Optional[int]
    revoked_at: Optional[int] = None


@dataclass(frozen=True)
class _PendingEnrollment:
    tenant_id: str
    license_id: str
    expires_at: int
    license_expires_at: Optional[int]


class RunnerStateStore(Protocol):
    def load(self) -> dict:
        ...

    def save(self, state: dict) -> None:
        ...


class SQLiteRunnerStateStore:
    """Single-record transactional state for one Runner registry.

    Only HMAC digests, installation metadata and expiry timestamps are stored.
    Enrollment codes, refresh tokens, access tokens and the signing key never
    enter this database.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runner_registry_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL, updated_at INTEGER NOT NULL)"
            )
        os.chmod(self.path, 0o600)

    def load(self) -> dict:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT payload FROM runner_registry_state WHERE singleton=1").fetchone()
        if row is None:
            return {}
        if not isinstance(row[0], str) or len(row[0].encode("utf-8")) > _MAX_STATE_BYTES:
            raise RuntimeError("runner registry state is corrupted")
        try:
            value = json.loads(row[0])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("runner registry state is corrupted") from exc
        if not isinstance(value, dict):
            raise RuntimeError("runner registry state is corrupted")
        return value

    def save(self, state: dict) -> None:
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if len(payload.encode("utf-8")) > _MAX_STATE_BYTES:
            raise RuntimeError("runner registry state exceeds safe size")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO runner_registry_state(singleton,payload,updated_at) VALUES(1,?,?) "
                    "ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                    (payload, int(time.time())),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise


def _identifier(value: str, label: str) -> str:
    cleaned = str(value).strip()
    if not _SAFE_ID.fullmatch(cleaned):
        raise ValueError("invalid %s" % label)
    return cleaned


def _encode(payload: bytes) -> str:
    return urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    try:
        decoded = urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise AccessDenied("invalid runner credential") from exc
    if _encode(decoded) != value:
        raise AccessDenied("invalid runner credential")
    return decoded


class RunnerRegistry:
    """In-memory reference contract for Runner enrollment and access.

    Secrets are returned only at activation/rotation and only HMAC digests are
    retained. A production adapter must persist the records transactionally and
    keep the signing key in a managed secret store; the public Runner never
    receives that server key.
    """

    def __init__(
        self,
        signing_key: bytes,
        *,
        clock: Callable[[], float] = time.time,
        access_ttl_seconds: int = 300,
        state_store: Optional[RunnerStateStore] = None,
    ) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("runner signing key must contain at least 32 bytes")
        if access_ttl_seconds < 60 or access_ttl_seconds > 900:
            raise ValueError("runner access TTL must be between 60 and 900 seconds")
        self._key = signing_key
        self._clock = clock
        self._access_ttl = int(access_ttl_seconds)
        self._key_fingerprint = sha256(signing_key).hexdigest()
        self._pending: Dict[str, _PendingEnrollment] = {}
        self._refresh: Dict[str, Tuple[str, str]] = {}
        self._installations: Dict[Tuple[str, str], RunnerInstallation] = {}
        self._lock = Lock()
        self._state_store = state_store
        self._restore()

    def _restore(self) -> None:
        if self._state_store is None:
            return
        state = self._state_store.load()
        if not state:
            return
        try:
            pending = state.get("pending", {})
            refresh = state.get("refresh", {})
            installations = state.get("installations", {})
            if state.get("format_version") != 1 or state.get("key_fingerprint") != self._key_fingerprint:
                raise ValueError
            if not all(isinstance(item, dict) for item in (pending, refresh, installations)) or sum(map(len, (pending, refresh, installations))) > 100_000:
                raise ValueError
            restored_pending = {}
            for digest, value in pending.items():
                item = _PendingEnrollment(**value)
                if not _DIGEST.fullmatch(str(digest)):
                    raise ValueError
                _identifier(item.tenant_id, "tenant_id")
                _identifier(item.license_id, "license_id")
                if int(item.expires_at) <= 0 or (item.license_expires_at is not None and int(item.license_expires_at) <= 0):
                    raise ValueError
                restored_pending[str(digest)] = item
            self._pending = restored_pending
            restored_refresh = {}
            for digest, value in refresh.items():
                if not _DIGEST.fullmatch(str(digest)) or not isinstance(value, list) or len(value) != 2:
                    raise ValueError
                restored_refresh[str(digest)] = (_identifier(value[0], "tenant_id"), _identifier(value[1], "installation_id"))
            self._refresh = restored_refresh
            self._installations = {}
            for value in installations.values():
                item = RunnerInstallation(**value)
                _identifier(item.tenant_id, "tenant_id")
                _identifier(item.installation_id, "installation_id")
                _identifier(item.license_id, "license_id")
                if item.platform not in _PLATFORMS or not _SAFE_VERSION.fullmatch(item.runner_version):
                    raise ValueError
                self._installations[(item.tenant_id, item.installation_id)] = item
            if any(value not in self._installations for value in self._refresh.values()):
                raise ValueError
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RuntimeError("runner registry state is corrupted") from exc

    def _persist_locked(self) -> None:
        if self._state_store is None:
            return
        state = {
            "format_version": 1,
            "key_fingerprint": self._key_fingerprint,
            "pending": {key: asdict(value) for key, value in self._pending.items()},
            "refresh": {key: list(value) for key, value in self._refresh.items()},
            "installations": {
                "%s:%s" % key: asdict(value) for key, value in self._installations.items()
            },
        }
        self._state_store.save(state)

    def _now(self) -> int:
        return int(self._clock())

    def _secret_digest(self, label: str, value: str) -> str:
        return hmac.new(self._key, (label + ":" + value).encode("utf-8"), sha256).hexdigest()

    @staticmethod
    def _active(installation: RunnerInstallation, now: int) -> bool:
        return installation.revoked_at is None and (
            installation.license_expires_at is None or installation.license_expires_at > now
        )

    def create_enrollment(
        self,
        tenant_id: str,
        license_id: str,
        *,
        ttl_seconds: int = 300,
        license_expires_at: Optional[int] = None,
    ) -> EnrollmentTicket:
        tenant = _identifier(tenant_id, "tenant_id")
        license_value = _identifier(license_id, "license_id")
        if ttl_seconds < 60 or ttl_seconds > 600:
            raise ValueError("enrollment TTL must be between 60 and 600 seconds")
        now = self._now()
        if license_expires_at is not None and int(license_expires_at) <= now:
            raise AccessDenied("license is not active")
        code = secrets.token_urlsafe(24)
        digest = self._secret_digest("enrollment", code)
        expires_at = now + int(ttl_seconds)
        with self._lock:
            self._prune(now)
            self._pending[digest] = _PendingEnrollment(
                tenant,
                license_value,
                expires_at,
                int(license_expires_at) if license_expires_at is not None else None,
            )
            self._persist_locked()
        return EnrollmentTicket(code, expires_at)

    def activate(
        self,
        code: str,
        installation_id: str,
        *,
        platform: str,
        runner_version: str,
    ) -> RunnerCredential:
        installation_value = _identifier(installation_id, "installation_id")
        platform_value = str(platform).strip().lower()
        version_value = str(runner_version).strip()
        if platform_value not in _PLATFORMS or not _SAFE_VERSION.fullmatch(version_value):
            raise ValueError("invalid Runner platform or version")
        now = self._now()
        digest = self._secret_digest("enrollment", str(code))
        with self._lock:
            pending = self._pending.pop(digest, None)
            if pending is not None:
                self._persist_locked()
            if pending is None or pending.expires_at <= now:
                raise AccessDenied("enrollment is invalid or expired")
            if pending.license_expires_at is not None and pending.license_expires_at <= now:
                raise AccessDenied("license is not active")
            installation_key = (pending.tenant_id, installation_value)
            existing = self._installations.get(installation_key)
            if existing is not None and existing.revoked_at is None:
                raise AccessDenied("installation is already active")
            installation = RunnerInstallation(
                pending.tenant_id,
                installation_value,
                pending.license_id,
                platform_value,
                version_value,
                now,
                now,
                pending.license_expires_at,
            )
            self._installations[installation_key] = installation
            credential = self._rotate_locked(installation, now)
            self._persist_locked()
            return credential

    def rotate(self, refresh_token: str) -> RunnerCredential:
        now = self._now()
        digest = self._secret_digest("refresh", str(refresh_token))
        with self._lock:
            installation_key = self._refresh.pop(digest, None)
            if installation_key is not None:
                self._persist_locked()
            installation = self._installations.get(installation_key or ("", ""))
            if installation is None or not self._active(installation, now):
                raise AccessDenied("runner credential is invalid or revoked")
            updated = RunnerInstallation(
                installation.tenant_id,
                installation.installation_id,
                installation.license_id,
                installation.platform,
                installation.runner_version,
                installation.created_at,
                now,
                installation.license_expires_at,
                installation.revoked_at,
            )
            self._installations[(installation.tenant_id, installation.installation_id)] = updated
            credential = self._rotate_locked(updated, now)
            self._persist_locked()
            return credential

    def _rotate_locked(self, installation: RunnerInstallation, now: int) -> RunnerCredential:
        refresh = secrets.token_urlsafe(32)
        self._refresh[self._secret_digest("refresh", refresh)] = (installation.tenant_id, installation.installation_id)
        expires_at = now + self._access_ttl
        payload = {
            "exp": expires_at,
            "iat": now,
            "installation_id": installation.installation_id,
            "iss": "olympus-cloud",
            "jti": secrets.token_urlsafe(16),
            "license_id": installation.license_id,
            "tenant_id": installation.tenant_id,
            "typ": "runner_access",
            "v": 1,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = _encode(body)
        signature = _encode(hmac.new(self._key, (_TOKEN_PREFIX + "." + encoded).encode("ascii"), sha256).digest())
        return RunnerCredential(installation.installation_id, refresh, "%s.%s.%s" % (_TOKEN_PREFIX, encoded, signature), expires_at)

    def verify(self, access_token: str, *, tenant_id: Optional[str] = None) -> RunnerClaims:
        if not isinstance(access_token, str) or len(access_token.encode("utf-8")) > _MAX_TOKEN_BYTES:
            raise AccessDenied("invalid runner credential")
        parts = access_token.split(".")
        if len(parts) != 3 or parts[0] != _TOKEN_PREFIX:
            raise AccessDenied("invalid runner credential")
        try:
            signing_input = (parts[0] + "." + parts[1]).encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise AccessDenied("invalid runner credential") from exc
        expected = hmac.new(self._key, signing_input, sha256).digest()
        if not hmac.compare_digest(expected, _decode(parts[2])):
            raise AccessDenied("invalid runner credential")
        try:
            payload = json.loads(_decode(parts[1]).decode("utf-8"))
            if payload.get("iss") != "olympus-cloud" or payload.get("typ") != "runner_access" or payload.get("v") != 1:
                raise AccessDenied("invalid runner credential")
            claims = RunnerClaims(
                _identifier(payload["tenant_id"], "tenant_id"),
                _identifier(payload["installation_id"], "installation_id"),
                _identifier(payload["license_id"], "license_id"),
                int(payload["iat"]),
                int(payload["exp"]),
                str(payload["jti"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            if isinstance(exc, AccessDenied):
                raise
            raise AccessDenied("invalid runner credential") from exc
        now = self._now()
        with self._lock:
            installation = self._installations.get((claims.tenant_id, claims.installation_id))
            if claims.expires_at <= now or claims.issued_at > now or installation is None or not self._active(installation, now):
                raise AccessDenied("runner credential is expired or revoked")
            if installation.tenant_id != claims.tenant_id or installation.license_id != claims.license_id:
                raise AccessDenied("runner credential does not match installation")
            if tenant_id is not None and claims.tenant_id != tenant_id:
                raise AccessDenied("runner credential belongs to another tenant")
        return claims

    def revoke(self, tenant_id: str, installation_id: str) -> RunnerInstallation:
        tenant = _identifier(tenant_id, "tenant_id")
        installation_value = _identifier(installation_id, "installation_id")
        now = self._now()
        with self._lock:
            installation_key = (tenant, installation_value)
            current = self._installations.get(installation_key)
            if current is None:
                raise AccessDenied("runner installation was not found")
            if current.revoked_at is not None:
                return current
            revoked = RunnerInstallation(
                current.tenant_id,
                current.installation_id,
                current.license_id,
                current.platform,
                current.runner_version,
                current.created_at,
                current.last_seen_at,
                current.license_expires_at,
                now,
            )
            self._installations[installation_key] = revoked
            stale = [digest for digest, value in self._refresh.items() if value == installation_key]
            for digest in stale:
                self._refresh.pop(digest, None)
            self._persist_locked()
            return revoked

    def list_installations(self, tenant_id: str) -> List[RunnerInstallation]:
        tenant = _identifier(tenant_id, "tenant_id")
        with self._lock:
            return sorted(
                (item for item in self._installations.values() if item.tenant_id == tenant),
                key=lambda item: (item.created_at, item.installation_id),
            )

    def _prune(self, now: int) -> None:
        stale = [digest for digest, item in self._pending.items() if item.expires_at <= now]
        for digest in stale:
            self._pending.pop(digest, None)
