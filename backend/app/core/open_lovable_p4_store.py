"""Open Lovable P4: bounded, owner-scoped *policy-only* reservation database.

This is not a remote sandbox lease or an attestation service. It never starts
processes, invokes inference, accesses networks, or marks a mission delivered.
For single-host lab qualification only. Production use is prohibited.
"""
from __future__ import annotations

import secrets
from contextlib import contextmanager
import sqlite3
import time
from pathlib import Path


class ReservationMissing(LookupError):
    pass


class ReservationConflict(ValueError):
    pass


class ReservationStore:
    MAX_ACTIVE_PER_TENANT = 10

    def __init__(self, database: str | Path) -> None:
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS reservations(
                reservation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                client_request_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('RESERVED_POLICY_ONLY','BLOCKED')),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(tenant_id,actor_id,client_request_id)
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id TEXT NOT NULL,
                code TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )""")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        try:
            connection.execute("PRAGMA busy_timeout=10000")
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _public(row) -> dict:
        return {
            "reservation_id": row[0],
            "project_id": row[3],
            "status": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "runtime_started": False,
            "model_calls": 0,
            "sandbox_id": None,
            "delivery_available": False,
        }

    def create(self, *, tenant_id: str, actor_id: str, project_id: str,
               client_request_id: str) -> dict:
        # Trusted identity must come from OLYMPUS permission dependency,
        # NEVER from an HTTP field. Validate nonempty even for direct callers.
        if not all(isinstance(v, str) and 1 <= len(v) <= 128
                   for v in (tenant_id, actor_id, project_id, client_request_id)):
            raise ReservationConflict("INVALID_RESERVATION_IDENTITY")
        now = int(time.time())
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute(
                "SELECT * FROM reservations WHERE tenant_id=? AND actor_id=? AND client_request_id=?",
                (tenant_id, actor_id, client_request_id)
            ).fetchone()
            if previous is not None:
                if previous[3] != project_id:
                    raise ReservationConflict("IDEMPOTENCY_KEY_PROJECT_MISMATCH")
                return self._public(previous)
            active = con.execute(
                "SELECT COUNT(*) FROM reservations WHERE tenant_id=? AND status='RESERVED_POLICY_ONLY'",
                (tenant_id,)
            ).fetchone()[0]
            if active >= self.MAX_ACTIVE_PER_TENANT:
                raise ReservationConflict("TENANT_POLICY_RESERVATION_LIMIT")
            rid = "olv_" + secrets.token_hex(16)
            con.execute(
                """INSERT INTO reservations
                (reservation_id,tenant_id,actor_id,project_id,client_request_id,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (rid, tenant_id, actor_id, project_id, client_request_id,
                 "RESERVED_POLICY_ONLY", now, now)
            )
            con.execute(
                "INSERT INTO events(reservation_id,code,created_at) VALUES (?,?,?)",
                (rid, "POLICY_RESERVATION_CREATED", now)
            )
            row = con.execute(
                "SELECT * FROM reservations WHERE reservation_id=?", (rid,)
            ).fetchone()
            return self._public(row)

    def _owned(self, con, *, reservation_id: str, tenant_id: str, actor_id: str):
        row = con.execute(
            "SELECT * FROM reservations WHERE reservation_id=? AND tenant_id=? AND actor_id=?",
            (reservation_id, tenant_id, actor_id)
        ).fetchone()
        if row is None:
            raise ReservationMissing("reservation not found")
        return row

    def owner_view(self, *, reservation_id: str, tenant_id: str, actor_id: str) -> dict:
        with self._connect() as con:
            return self._public(self._owned(
                con, reservation_id=reservation_id, tenant_id=tenant_id, actor_id=actor_id
            ))

    def block(self, *, reservation_id: str, tenant_id: str, actor_id: str) -> dict:
        now = int(time.time())
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._owned(con, reservation_id=reservation_id,
                              tenant_id=tenant_id, actor_id=actor_id)
            if row[5] != "BLOCKED":
                con.execute(
                    "UPDATE reservations SET status='BLOCKED',updated_at=? WHERE reservation_id=?",
                    (now, reservation_id)
                )
                con.execute(
                    "INSERT INTO events(reservation_id,code,created_at) VALUES (?,?,?)",
                    (reservation_id, "OWNER_BLOCKED_POLICY_RESERVATION", now)
                )
            row = self._owned(con, reservation_id=reservation_id,
                              tenant_id=tenant_id, actor_id=actor_id)
            return self._public(row)
