from dataclasses import dataclass
import hashlib
import re
from typing import Optional

_SAFE = re.compile(r"[^a-z0-9._-]+")

@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str
    tenant_id: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_id_for(email: str) -> str:
    return "usr_" + hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:16]


def tenant_id_for(email: str) -> str:
    # Default single-user tenant is deterministic and isolated per identity.
    return "tnt_" + hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:16]


def identity_for(email: str) -> Identity:
    normalized = normalize_email(email)
    return Identity(user_id_for(normalized), normalized, tenant_id_for(normalized))


def safe_tenant_id(value: str) -> str:
    cleaned = _SAFE.sub("-", value.strip().lower()).strip("-._")
    return cleaned[:64] or "tenant"
