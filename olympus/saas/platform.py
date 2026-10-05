from __future__ import annotations

from dataclasses import dataclass
from hashlib import pbkdf2_hmac, sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from typing import Mapping, Optional


_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_ROLES = ("owner", "admin", "builder", "viewer")
_PERMISSIONS = {
    "owner": frozenset({"*"}),
    "admin": frozenset({
        "organization.read", "organization.update", "members.read", "members.manage",
        "projects.read", "projects.write", "missions.run", "deployments.manage",
        "audit.read", "usage.read",
    }),
    "builder": frozenset({
        "organization.read", "members.read", "projects.read", "projects.write",
        "missions.run", "deployments.manage", "usage.read",
    }),
    "viewer": frozenset({"organization.read", "members.read", "projects.read", "usage.read"}),
}

# Commercial prices deliberately live outside the product core. These capability
# limits are safe operational defaults and can be replaced by a billing provider.
_PLAN_LIMITS = {
    "founder": {"members": 25, "projects": 250, "missions_month": 5000, "deployments_month": 500},
    "starter": {"members": 1, "projects": 5, "missions_month": 100, "deployments_month": 10},
    "professional": {"members": 10, "projects": 100, "missions_month": 2000, "deployments_month": 200},
    "business": {"members": 100, "projects": 1000, "missions_month": 20000, "deployments_month": 2000},
}


class AuthorizationError(PermissionError):
    pass


class EntitlementError(RuntimeError):
    pass


@dataclass(frozen=True)
class Organization:
    organization_id: str
    name: str
    slug: str
    owner_user_id: str
    plan_id: str
    subscription_status: str
    created_at: float


@dataclass(frozen=True)
class Member:
    organization_id: str
    user_id: str
    email: str
    role: str
    status: str
    joined_at: float


@dataclass(frozen=True)
class Invitation:
    invitation_id: str
    organization_id: str
    email: str
    role: str
    expires_at: float
    accepted_at: Optional[float]


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    organization_id: str
    actor_user_id: str
    action: str
    target_type: str
    target_id: str
    details: dict
    created_at: float
    previous_hash: str
    event_hash: str


@dataclass(frozen=True)
class BillingEvent:
    provider: str
    event_id: str
    organization_id: str
    plan_id: str
    subscription_status: str
    customer_reference: Optional[str] = None
    subscription_reference: Optional[str] = None


def _identifier(value: str, field: str) -> str:
    cleaned = str(value or "").strip().lower()
    if not _ID.fullmatch(cleaned):
        raise ValueError("invalid %s" % field)
    return cleaned


def _email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) > 254 or normalized.count("@") != 1 or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("invalid email")
    return normalized


def _role(value: str, allow_owner: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    allowed = _ROLES if allow_owner else _ROLES[1:]
    if normalized not in allowed:
        raise ValueError("invalid role")
    return normalized


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned[:63] or "workspace"


def _canonical(value: Mapping) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _password_hash(password: str, *, salt: Optional[bytes] = None, rounds: int = 600_000) -> str:
    if len(password) < 10 or len(password) > 1024:
        raise ValueError("password must contain between 10 and 1024 characters")
    actual_salt = salt or secrets.token_bytes(24)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt, rounds)
    return "pbkdf2_sha256$%d$%s$%s" % (rounds, actual_salt.hex(), digest.hex())


def _password_valid(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256" or int(rounds) < 100_000:
            return False
        actual = _password_hash(password, salt=bytes.fromhex(salt), rounds=int(rounds)).split("$", 3)[3]
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


class SaaSPlatform:
    """Transactional organizations, RBAC, audit, entitlements and billing state.

    Raw invitation tokens and passwords are never persisted. Billing events are
    accepted only after a provider adapter has verified their authenticity.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users(
                    user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT,
                    status TEXT NOT NULL DEFAULT 'active', created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS organizations(
                    organization_id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
                    owner_user_id TEXT NOT NULL, plan_id TEXT NOT NULL DEFAULT 'founder',
                    subscription_status TEXT NOT NULL DEFAULT 'active', customer_reference TEXT,
                    subscription_reference TEXT, created_at REAL NOT NULL,
                    FOREIGN KEY(owner_user_id) REFERENCES users(user_id)
                );
                CREATE TABLE IF NOT EXISTS memberships(
                    organization_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active', joined_at REAL NOT NULL,
                    PRIMARY KEY(organization_id,user_id),
                    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                CREATE TABLE IF NOT EXISTS invitations(
                    invitation_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, email TEXT NOT NULL,
                    role TEXT NOT NULL, token_digest TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL,
                    accepted_at REAL, created_at REAL NOT NULL,
                    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id)
                );
                CREATE TABLE IF NOT EXISTS usage_counters(
                    organization_id TEXT NOT NULL, metric TEXT NOT NULL, period TEXT NOT NULL,
                    quantity INTEGER NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(organization_id,metric,period),
                    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id)
                );
                CREATE TABLE IF NOT EXISTS billing_events(
                    provider TEXT NOT NULL, event_id TEXT NOT NULL, organization_id TEXT NOT NULL,
                    received_at REAL NOT NULL, PRIMARY KEY(provider,event_id),
                    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, organization_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL, details_json TEXT NOT NULL, created_at REAL NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE,
                    FOREIGN KEY(organization_id) REFERENCES organizations(organization_id)
                );
                CREATE INDEX IF NOT EXISTS audit_org_sequence_idx ON audit_events(organization_id,sequence);
                CREATE INDEX IF NOT EXISTS memberships_user_idx ON memberships(user_id,status);
            """)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _organization(row: sqlite3.Row) -> Organization:
        return Organization(row["organization_id"], row["name"], row["slug"], row["owner_user_id"], row["plan_id"], row["subscription_status"], row["created_at"])

    def bootstrap_owner(self, user_id: str, email: str, organization_id: str, name: str = "Meu Olympus") -> Organization:
        user = _identifier(user_id, "user_id")
        address = _email(email)
        organization = _identifier(organization_id, "organization_id")
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("INSERT OR IGNORE INTO users(user_id,email,created_at) VALUES(?,?,?)", (user, address, now))
                row = connection.execute("SELECT * FROM organizations WHERE organization_id=?", (organization,)).fetchone()
                if row is None:
                    base_slug = _slug(name)
                    slug = base_slug
                    suffix = 1
                    while connection.execute("SELECT 1 FROM organizations WHERE slug=?", (slug,)).fetchone():
                        suffix += 1
                        slug = (base_slug[:55] + "-" + str(suffix))[:63]
                    connection.execute(
                        "INSERT INTO organizations(organization_id,name,slug,owner_user_id,created_at) VALUES(?,?,?,?,?)",
                        (organization, str(name).strip()[:120] or "Meu Olympus", slug, user, now),
                    )
                    connection.execute(
                        "INSERT INTO memberships(organization_id,user_id,role,joined_at) VALUES(?,?,?,?)",
                        (organization, user, "owner", now),
                    )
                    self._append_audit(connection, organization, user, "organization.created", "organization", organization, {"name": str(name).strip()[:120]})
                    row = connection.execute("SELECT * FROM organizations WHERE organization_id=?", (organization,)).fetchone()
                elif not connection.execute("SELECT 1 FROM memberships WHERE organization_id=? AND user_id=? AND status='active'", (organization, user)).fetchone():
                    raise AuthorizationError("user is not a member of this organization")
                connection.commit()
                return self._organization(row)
            except Exception:
                connection.rollback()
                raise

    def create_organization(self, user_id: str, email: str, name: str) -> Organization:
        user = _identifier(user_id, "user_id")
        address = _email(email)
        display_name = str(name or "").strip()
        if len(display_name) < 2 or len(display_name) > 120:
            raise ValueError("organization name must contain between 2 and 120 characters")
        now = time.time()
        organization = "org_" + secrets.token_hex(12)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("INSERT OR IGNORE INTO users(user_id,email,created_at) VALUES(?,?,?)", (user, address, now))
                base_slug = _slug(display_name)
                slug = base_slug
                while connection.execute("SELECT 1 FROM organizations WHERE slug=?", (slug,)).fetchone():
                    slug = (base_slug[:50] + "-" + secrets.token_hex(4))[:63]
                connection.execute(
                    "INSERT INTO organizations(organization_id,name,slug,owner_user_id,created_at) VALUES(?,?,?,?,?)",
                    (organization, display_name, slug, user, now),
                )
                connection.execute("INSERT INTO memberships(organization_id,user_id,role,joined_at) VALUES(?,?,?,?)", (organization, user, "owner", now))
                self._append_audit(connection, organization, user, "organization.created", "organization", organization, {"name": display_name})
                row = connection.execute("SELECT * FROM organizations WHERE organization_id=?", (organization,)).fetchone()
                connection.commit()
                return self._organization(row)
            except Exception:
                connection.rollback()
                raise

    def get_organization(self, organization_id: str) -> Optional[Organization]:
        organization = _identifier(organization_id, "organization_id")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM organizations WHERE organization_id=?", (organization,)).fetchone()
        return self._organization(row) if row else None

    def organizations_for(self, user_id: str) -> tuple[Organization, ...]:
        user = _identifier(user_id, "user_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT o.* FROM organizations o JOIN memberships m ON m.organization_id=o.organization_id WHERE m.user_id=? AND m.status='active' ORDER BY o.created_at",
                (user,),
            ).fetchall()
        return tuple(self._organization(row) for row in rows)

    def role_for(self, organization_id: str, user_id: str) -> Optional[str]:
        organization = _identifier(organization_id, "organization_id")
        user = _identifier(user_id, "user_id")
        with self._connect() as connection:
            row = connection.execute("SELECT role FROM memberships WHERE organization_id=? AND user_id=? AND status='active'", (organization, user)).fetchone()
        return str(row["role"]) if row else None

    def authorize(self, organization_id: str, user_id: str, permission: str) -> str:
        role = self.role_for(organization_id, user_id)
        if role is None:
            raise AuthorizationError("organization membership required")
        permissions = _PERMISSIONS.get(role, frozenset())
        if "*" not in permissions and permission not in permissions:
            raise AuthorizationError("permission denied")
        return role

    def list_members(self, organization_id: str, actor_user_id: str) -> tuple[Member, ...]:
        self.authorize(organization_id, actor_user_id, "members.read")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT m.organization_id,m.user_id,u.email,m.role,m.status,m.joined_at FROM memberships m JOIN users u ON u.user_id=m.user_id WHERE m.organization_id=? ORDER BY m.joined_at",
                (organization_id,),
            ).fetchall()
        return tuple(Member(row["organization_id"], row["user_id"], row["email"], row["role"], row["status"], row["joined_at"]) for row in rows)

    def invite(self, organization_id: str, actor_user_id: str, email: str, role: str, ttl_seconds: int = 7 * 86400) -> tuple[Invitation, str]:
        organization = _identifier(organization_id, "organization_id")
        actor = _identifier(actor_user_id, "actor_user_id")
        address = _email(email)
        selected_role = _role(role)
        if ttl_seconds < 300 or ttl_seconds > 30 * 86400:
            raise ValueError("invalid invitation lifetime")
        self.authorize(organization, actor, "members.manage")
        self.assert_capacity(organization, "members", self.member_count(organization) + 1)
        token = secrets.token_urlsafe(32)
        invitation_id = "inv_" + secrets.token_hex(12)
        now = time.time()
        expires = now + ttl_seconds
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if connection.execute("SELECT 1 FROM users u JOIN memberships m ON m.user_id=u.user_id WHERE m.organization_id=? AND u.email=? AND m.status='active'", (organization, address)).fetchone():
                    raise ValueError("user is already a member")
                connection.execute(
                    "INSERT INTO invitations(invitation_id,organization_id,email,role,token_digest,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
                    (invitation_id, organization, address, selected_role, sha256(token.encode()).hexdigest(), expires, now),
                )
                self._append_audit(connection, organization, actor, "member.invited", "invitation", invitation_id, {"email": address, "role": selected_role})
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return Invitation(invitation_id, organization, address, selected_role, expires, None), token

    def accept_invitation(self, token: str, user_id: str, email: str, password: str) -> Member:
        digest = sha256(str(token).encode()).hexdigest()
        user = _identifier(user_id, "user_id")
        address = _email(email)
        encoded = _password_hash(password)
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT * FROM invitations WHERE token_digest=?", (digest,)).fetchone()
                if row is None or row["accepted_at"] is not None or float(row["expires_at"]) <= now or row["email"] != address:
                    raise AuthorizationError("invitation is invalid or expired")
                self.assert_capacity(row["organization_id"], "members", self.member_count(row["organization_id"]) + 1)
                existing = connection.execute("SELECT user_id,password_hash FROM users WHERE email=?", (address,)).fetchone()
                if existing and existing["user_id"] != user:
                    raise AuthorizationError("account identity mismatch")
                if existing and existing["password_hash"]:
                    if not _password_valid(password, existing["password_hash"]):
                        raise AuthorizationError("existing account password does not match")
                else:
                    connection.execute(
                        "INSERT INTO users(user_id,email,password_hash,created_at) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET password_hash=excluded.password_hash",
                        (user, address, encoded, now),
                    )
                connection.execute(
                    "INSERT INTO memberships(organization_id,user_id,role,joined_at) VALUES(?,?,?,?) ON CONFLICT(organization_id,user_id) DO UPDATE SET role=excluded.role,status='active'",
                    (row["organization_id"], user, row["role"], now),
                )
                connection.execute("UPDATE invitations SET accepted_at=? WHERE invitation_id=? AND accepted_at IS NULL", (now, row["invitation_id"]))
                self._append_audit(connection, row["organization_id"], user, "member.joined", "user", user, {"role": row["role"]})
                connection.commit()
                return Member(row["organization_id"], user, address, row["role"], "active", now)
            except Exception:
                connection.rollback()
                raise

    def authenticate(self, email: str, password: str) -> Optional[tuple[str, str]]:
        address = _email(email)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT u.user_id,u.password_hash,m.organization_id FROM users u JOIN memberships m ON m.user_id=u.user_id WHERE u.email=? AND u.status='active' AND m.status='active' ORDER BY m.joined_at LIMIT 1",
                (address,),
            ).fetchone()
        if row is None or not row["password_hash"] or not _password_valid(password, row["password_hash"]):
            return None
        return str(row["user_id"]), str(row["organization_id"])

    def update_member_role(self, organization_id: str, actor_user_id: str, member_user_id: str, role: str) -> Member:
        organization = _identifier(organization_id, "organization_id")
        actor = _identifier(actor_user_id, "actor_user_id")
        member = _identifier(member_user_id, "member_user_id")
        selected = _role(role)
        self.authorize(organization, actor, "members.manage")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT m.*,u.email FROM memberships m JOIN users u ON u.user_id=m.user_id WHERE m.organization_id=? AND m.user_id=?", (organization, member)).fetchone()
                if row is None:
                    raise KeyError("member not found")
                if row["role"] == "owner":
                    raise AuthorizationError("organization owner role cannot be changed")
                connection.execute("UPDATE memberships SET role=? WHERE organization_id=? AND user_id=?", (selected, organization, member))
                self._append_audit(connection, organization, actor, "member.role_updated", "user", member, {"from": row["role"], "to": selected})
                connection.commit()
                return Member(organization, member, row["email"], selected, row["status"], row["joined_at"])
            except Exception:
                connection.rollback()
                raise

    def remove_member(self, organization_id: str, actor_user_id: str, member_user_id: str) -> None:
        organization = _identifier(organization_id, "organization_id")
        actor = _identifier(actor_user_id, "actor_user_id")
        member = _identifier(member_user_id, "member_user_id")
        self.authorize(organization, actor, "members.manage")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT role FROM memberships WHERE organization_id=? AND user_id=? AND status='active'", (organization, member)).fetchone()
                if row is None:
                    raise KeyError("member not found")
                if row["role"] == "owner":
                    raise AuthorizationError("organization owner cannot be removed")
                connection.execute("UPDATE memberships SET status='removed' WHERE organization_id=? AND user_id=?", (organization, member))
                self._append_audit(connection, organization, actor, "member.removed", "user", member, {})
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def member_count(self, organization_id: str) -> int:
        organization = _identifier(organization_id, "organization_id")
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM memberships WHERE organization_id=? AND status='active'", (organization,)).fetchone()[0])

    def entitlements(self, organization_id: str) -> dict:
        organization = self.get_organization(organization_id)
        if organization is None:
            raise KeyError("organization not found")
        limits = dict(_PLAN_LIMITS.get(organization.plan_id, _PLAN_LIMITS["starter"]))
        return {"plan_id": organization.plan_id, "subscription_status": organization.subscription_status, "limits": limits}

    def assert_capacity(self, organization_id: str, metric: str, desired_quantity: int) -> None:
        entitlements = self.entitlements(organization_id)
        if entitlements["subscription_status"] not in {"active", "trialing"}:
            raise EntitlementError("subscription is not active")
        limit = entitlements["limits"].get(metric)
        if limit is not None and desired_quantity > int(limit):
            raise EntitlementError("plan limit exceeded for %s" % metric)

    @staticmethod
    def _period(now: Optional[float] = None) -> str:
        return time.strftime("%Y-%m", time.gmtime(now or time.time()))

    def consume(self, organization_id: str, actor_user_id: str, metric: str, quantity: int = 1, period: Optional[str] = None) -> int:
        organization = _identifier(organization_id, "organization_id")
        actor = _identifier(actor_user_id, "actor_user_id")
        if metric not in {"missions_month", "deployments_month"} or quantity < 1 or quantity > 1000:
            raise ValueError("invalid usage metric or quantity")
        self.authorize(organization, actor, "missions.run" if metric == "missions_month" else "deployments.manage")
        selected_period = period or self._period()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT quantity FROM usage_counters WHERE organization_id=? AND metric=? AND period=?", (organization, metric, selected_period)).fetchone()
                desired = (int(row["quantity"]) if row else 0) + quantity
                self.assert_capacity(organization, metric, desired)
                connection.execute(
                    "INSERT INTO usage_counters(organization_id,metric,period,quantity,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(organization_id,metric,period) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at",
                    (organization, metric, selected_period, desired, time.time()),
                )
                connection.commit()
                return desired
            except Exception:
                connection.rollback()
                raise

    def usage(self, organization_id: str, actor_user_id: str, period: Optional[str] = None) -> dict:
        organization = _identifier(organization_id, "organization_id")
        self.authorize(organization, actor_user_id, "usage.read")
        selected_period = period or self._period()
        with self._connect() as connection:
            rows = connection.execute("SELECT metric,quantity FROM usage_counters WHERE organization_id=? AND period=?", (organization, selected_period)).fetchall()
        return {"period": selected_period, "usage": {row["metric"]: int(row["quantity"]) for row in rows}, **self.entitlements(organization)}

    def refund(self, organization_id: str, actor_user_id: str, metric: str, quantity: int = 1, period: Optional[str] = None) -> int:
        organization = _identifier(organization_id, "organization_id")
        actor = _identifier(actor_user_id, "actor_user_id")
        if metric not in {"missions_month", "deployments_month"} or quantity < 1:
            raise ValueError("invalid usage metric or quantity")
        self.authorize(organization, actor, "missions.run" if metric == "missions_month" else "deployments.manage")
        selected_period = period or self._period()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT quantity FROM usage_counters WHERE organization_id=? AND metric=? AND period=?", (organization, metric, selected_period)).fetchone()
                remaining = max(0, (int(row["quantity"]) if row else 0) - quantity)
                connection.execute(
                    "INSERT INTO usage_counters(organization_id,metric,period,quantity,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(organization_id,metric,period) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at",
                    (organization, metric, selected_period, remaining, time.time()),
                )
                connection.commit()
                return remaining
            except Exception:
                connection.rollback()
                raise

    def apply_verified_billing_event(self, event: BillingEvent, actor_user_id: str = "system") -> bool:
        provider = _identifier(event.provider, "provider")
        event_id = _identifier(event.event_id, "event_id")
        organization = _identifier(event.organization_id, "organization_id")
        plan = _identifier(event.plan_id, "plan_id")
        if plan not in _PLAN_LIMITS or event.subscription_status not in {"active", "trialing", "past_due", "canceled", "paused"}:
            raise ValueError("unsupported billing state")
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if connection.execute("SELECT 1 FROM organizations WHERE organization_id=?", (organization,)).fetchone() is None:
                    raise KeyError("organization not found")
                inserted = connection.execute("INSERT OR IGNORE INTO billing_events(provider,event_id,organization_id,received_at) VALUES(?,?,?,?)", (provider, event_id, organization, time.time())).rowcount
                if not inserted:
                    connection.rollback()
                    return False
                connection.execute(
                    "UPDATE organizations SET plan_id=?,subscription_status=?,customer_reference=?,subscription_reference=? WHERE organization_id=?",
                    (plan, event.subscription_status, event.customer_reference, event.subscription_reference, organization),
                )
                self._append_audit(connection, organization, actor_user_id, "billing.subscription_updated", "subscription", event.subscription_reference or event_id, {"provider": provider, "plan_id": plan, "status": event.subscription_status})
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    def _append_audit(self, connection: sqlite3.Connection, organization_id: str, actor_user_id: str, action: str, target_type: str, target_id: str, details: Mapping) -> None:
        previous = connection.execute("SELECT event_hash FROM audit_events WHERE organization_id=? ORDER BY sequence DESC LIMIT 1", (organization_id,)).fetchone()
        previous_hash = str(previous["event_hash"]) if previous else "0" * 64
        created_at = time.time()
        body = {"organization_id": organization_id, "actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "details": dict(details), "created_at": created_at, "previous_hash": previous_hash}
        event_hash = sha256(_canonical(body).encode("utf-8")).hexdigest()
        connection.execute(
            "INSERT INTO audit_events(organization_id,actor_user_id,action,target_type,target_id,details_json,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)",
            (organization_id, actor_user_id, action, target_type, target_id, _canonical(dict(details)), created_at, previous_hash, event_hash),
        )

    def audit(self, organization_id: str, actor_user_id: str, limit: int = 100) -> tuple[AuditEvent, ...]:
        organization = _identifier(organization_id, "organization_id")
        self.authorize(organization, actor_user_id, "audit.read")
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events WHERE organization_id=? ORDER BY sequence DESC LIMIT ?", (organization, safe_limit)).fetchall()
        return tuple(AuditEvent(row["sequence"], row["organization_id"], row["actor_user_id"], row["action"], row["target_type"], row["target_id"], json.loads(row["details_json"]), row["created_at"], row["previous_hash"], row["event_hash"]) for row in rows)

    def record_action(self, organization_id: str, actor_user_id: str, action: str, target_type: str, target_id: str, details: Optional[Mapping] = None) -> None:
        organization = _identifier(organization_id, "organization_id")
        actor = _identifier(actor_user_id, "actor_user_id")
        if self.role_for(organization, actor) is None:
            raise AuthorizationError("organization membership required")
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,100}", action):
            raise ValueError("invalid audit action")
        safe_target_type = _identifier(target_type, "target_type")
        safe_target_id = str(target_id or "").strip()[:200]
        safe_details = json.loads(_canonical(dict(details or {})))
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._append_audit(connection, organization, actor, action, safe_target_type, safe_target_id, safe_details)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def verify_audit_chain(self, organization_id: str) -> bool:
        organization = _identifier(organization_id, "organization_id")
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events WHERE organization_id=? ORDER BY sequence", (organization,)).fetchall()
        previous_hash = "0" * 64
        for row in rows:
            body = {"organization_id": row["organization_id"], "actor_user_id": row["actor_user_id"], "action": row["action"], "target_type": row["target_type"], "target_id": row["target_id"], "details": json.loads(row["details_json"]), "created_at": row["created_at"], "previous_hash": previous_hash}
            expected = sha256(_canonical(body).encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous_hash or not hmac.compare_digest(row["event_hash"], expected):
                return False
            previous_hash = row["event_hash"]
        return True
