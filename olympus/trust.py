from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Tuple
import os


class TrustDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_USER = "require_user"
    BLOCK = "block"


@dataclass(frozen=True)
class TrustResult:
    decision: TrustDecision
    reason: str


PROTECTED_CORE_PREFIXES: Tuple[str, ...] = (
    "olympus/trust.py",
    "backend/app/core/security.py",
    "backend/app/core/tenancy.py",
    "olympus/agent/verification_engine.py",
    "olympus/skills/policy.py",
)

SECRET_BASENAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
SECRET_TOKENS = ("api_key", "apikey", "password", "passwd", "secret", "private_key", "access_token", "refresh_token")


def normalize_relative_path(root: str, candidate: str) -> Path:
    root_path = Path(root).resolve()
    raw = Path(candidate)
    if raw.is_absolute():
        raise PermissionError("absolute path is not allowed")
    target = (root_path / raw).resolve()
    try:
        target.relative_to(root_path)
    except ValueError as exc:
        raise PermissionError("path escapes workspace") from exc
    return target


def is_protected_core(relative_path: str, protected: Iterable[str] = PROTECTED_CORE_PREFIXES) -> bool:
    normalized = str(Path(relative_path)).replace("\\", "/").lstrip("./")
    return any(normalized == p or normalized.startswith(p.rstrip("/") + "/") for p in protected)


def looks_secret(relative_path: str) -> bool:
    p = Path(relative_path)
    name = p.name.lower()
    stem = p.stem.lower()
    return name in SECRET_BASENAMES or any(token in name or token in stem for token in SECRET_TOKENS)


class TrustBoundary:
    """System-owned policy. Model output cannot relax this boundary."""

    def authorize_file_action(self, root: str, relative_path: str, write: bool = False) -> TrustResult:
        try:
            normalize_relative_path(root, relative_path)
        except PermissionError as exc:
            return TrustResult(TrustDecision.BLOCK, str(exc))
        if looks_secret(relative_path):
            return TrustResult(TrustDecision.BLOCK, "secret material is never exposed to agent actions")
        if write and is_protected_core(relative_path):
            return TrustResult(TrustDecision.REQUIRE_USER, "protected core modification requires explicit authorization")
        return TrustResult(TrustDecision.ALLOW, "within trust boundary")


def production_secret_is_safe() -> bool:
    env = os.environ.get("OLYMPUS_ENV", "development").strip().lower()
    secret = os.environ.get("OLYMPUS_JWT_SECRET", "")
    if env not in {"production", "prod"}:
        return True
    return len(secret) >= 32 and "troque" not in secret.lower() and "dev-secret" not in secret.lower()
