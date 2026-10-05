from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager


class DecisionStatus(str, Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    EXPIRED = "expired"


@dataclass(frozen=True)
class DecisionRequest:
    decision_id: str
    execution_id: str
    tenant_id: str
    question: str
    options: List[Dict[str, Any]]
    context: Dict[str, Any]
    status: str
    created_at: float
    expires_at: Optional[float]
    answered_at: Optional[float] = None
    choice_json: Optional[str] = None
    comment: Optional[str] = None


class DecisionStore:
    """Durable, tenant-scoped human-decision store with exactly-once answers."""

    def __init__(self, path: str) -> None:
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS decision_requests (
                decision_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                context_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                answered_at REAL,
                choice_json TEXT,
                comment TEXT
            )""")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create(self, execution_id: str, tenant_id: str, question: str,
               options: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None,
               ttl_seconds: Optional[float] = None) -> DecisionRequest:
        if not question.strip():
            raise ValueError("decision question is required")
        if not options:
            raise ValueError("decision options are required")
        now = time.time()
        expires_at = now + float(ttl_seconds) if ttl_seconds is not None else None
        decision_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO decision_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (decision_id, execution_id, tenant_id, question.strip(),
                 json.dumps(options, ensure_ascii=False), json.dumps(context or {}, ensure_ascii=False),
                 DecisionStatus.PENDING.value, now, expires_at, None, None, None),
            )
        return self.get(decision_id, tenant_id)

    def get(self, decision_id: str, tenant_id: str) -> Optional[DecisionRequest]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM decision_requests WHERE decision_id=? AND tenant_id=?",
                (decision_id, tenant_id),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        if data["status"] == DecisionStatus.PENDING.value and data["expires_at"] is not None and data["expires_at"] <= time.time():
            with self._connect() as conn:
                conn.execute("UPDATE decision_requests SET status=? WHERE decision_id=? AND status=?",
                             (DecisionStatus.EXPIRED.value, decision_id, DecisionStatus.PENDING.value))
            data["status"] = DecisionStatus.EXPIRED.value
        return DecisionRequest(
            decision_id=data["decision_id"], execution_id=data["execution_id"], tenant_id=data["tenant_id"],
            question=data["question"], options=json.loads(data["options_json"]), context=json.loads(data["context_json"]),
            status=data["status"], created_at=data["created_at"], expires_at=data["expires_at"],
            answered_at=data["answered_at"], choice_json=data["choice_json"], comment=data["comment"],
        )

    def answer(self, decision_id: str, tenant_id: str, choice: Any, comment: Optional[str] = None) -> DecisionRequest:
        current = self.get(decision_id, tenant_id)
        if current is None:
            raise KeyError("decision not found")
        if current.status == DecisionStatus.EXPIRED.value:
            raise TimeoutError("decision expired")
        if current.status != DecisionStatus.PENDING.value:
            raise RuntimeError("decision already answered")
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE decision_requests SET status=?,answered_at=?,choice_json=?,comment=? WHERE decision_id=? AND tenant_id=? AND status=?",
                (DecisionStatus.ANSWERED.value, now, json.dumps(choice, ensure_ascii=False), comment,
                 decision_id, tenant_id, DecisionStatus.PENDING.value),
            )
            if cur.rowcount != 1:
                raise RuntimeError("decision already answered")
        return self.get(decision_id, tenant_id)
