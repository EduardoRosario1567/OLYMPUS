from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from threading import Event, Lock, RLock, Thread
import json
import os
import shutil
import sqlite3
import time
import traceback
import uuid
from typing import Callable, Dict, List, Optional

from .project_workspace import ProjectWorkspaceManager
from .project_versions import ProjectVersionStore
from .decisions import DecisionStore
from olympus.agent.verifier import AgentVerifier
from olympus.agent.acceptance import compile_contract, format_failures, snapshot
from olympus.agent.mission_compiler import MissionCompiler
from olympus.memory import MemoryContextProvider, MemoryType, Sensitivity, MemoryWriter
from contextlib import contextmanager


MAX_EVENT_PAYLOAD_BYTES = 64 * 1024


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    WAITING_DECISION = "waiting_decision"
    PAUSED_CAPACITY = "paused_capacity"
    LEGACY_WAITING_CAPACITY = "waiting_capacity"


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    project_id: str
    mission_id: str
    task: str
    status: str
    created_at: float
    updated_at: float
    workspace: Optional[str] = None
    error: Optional[str] = None
    result_summary: Optional[str] = None
    resume_count: int = 0
    max_iterations: int = 12
    attempt_count: int = 0
    lease_until: Optional[float] = None
    tenant_id: str = "local"
    user_id: str = "local"
    lease_owner: Optional[str] = None


class _Store:
    def __init__(self, path: str) -> None:
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        with self._connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    mission_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    workspace TEXT,
                    error TEXT,
                    result_summary TEXT,
                    resume_count INTEGER NOT NULL DEFAULT 0,
                    max_iterations INTEGER NOT NULL DEFAULT 12,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL,
                    tenant_id TEXT NOT NULL DEFAULT 'local',
                    user_id TEXT NOT NULL DEFAULT 'local',
                    lease_owner TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS execution_events (
                    execution_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    at REAL NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(execution_id, seq)
                )"""
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(executions)").fetchall()}
            if "max_iterations" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN max_iterations INTEGER NOT NULL DEFAULT 12")
            if "attempt_count" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "lease_until" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN lease_until REAL")
            if "tenant_id" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'local'")
            if "user_id" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")
            if "lease_owner" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN lease_owner TEXT")

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create(self, project_id: str, mission_id: str, task: str, max_iterations: int = 12, tenant_id: str = "local", user_id: str = "local") -> ExecutionRecord:
        now = time.time()
        execution_id = uuid.uuid4().hex[:16]
        rec = ExecutionRecord(execution_id, project_id, mission_id, task, ExecutionStatus.QUEUED.value, now, now, None, None, None, 0, int(max_iterations), 0, None, tenant_id, user_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO executions (execution_id,project_id,mission_id,task,status,created_at,updated_at,workspace,error,result_summary,resume_count,max_iterations,attempt_count,lease_until,tenant_id,user_id,lease_owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rec.execution_id, rec.project_id, rec.mission_id, rec.task, rec.status,
                 rec.created_at, rec.updated_at, None, None, None, rec.resume_count, int(max_iterations), 0, None, tenant_id, user_id, None),
            )
        self.event(execution_id, "queued")
        return rec

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM executions WHERE execution_id=?", (execution_id,)).fetchone()
        return ExecutionRecord(**dict(row)) if row else None

    def list(self, tenant_id: str, limit: int = 100, project_id: Optional[str] = None, status: Optional[str] = None) -> List[ExecutionRecord]:
        clauses = ["tenant_id=?"]
        values: list = [tenant_id]
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if status:
            clauses.append("status=?")
            values.append(status)
        values.append(max(1, min(int(limit), 500)))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM executions WHERE %s ORDER BY created_at DESC LIMIT ?" % " AND ".join(clauses),
                values,
            ).fetchall()
        return [ExecutionRecord(**dict(row)) for row in rows]

    def update(self, execution_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        assignments = ", ".join("%s=?" % k for k in fields)
        values = list(fields.values()) + [execution_id]
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE executions SET %s WHERE execution_id=?" % assignments, values)

    def event(self, execution_id: str, event: str, **payload) -> dict:
        now = time.time()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if len(encoded.encode("utf-8")) > MAX_EVENT_PAYLOAD_BYTES:
            payload = {
                "truncated": True,
                "payload_bytes": len(encoded.encode("utf-8")),
                "summary": "event payload exceeded the configured retention limit",
            }
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS n FROM execution_events WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            seq = int(row["n"]) + 1
            conn.execute(
                "INSERT INTO execution_events VALUES (?, ?, ?, ?, ?)",
                (execution_id, seq, event, now, encoded),
            )
        return {"seq": seq, "event": event, "at": now, **payload}

    def prune_events(self, older_than: float) -> int:
        """Bound event storage without deleting the execution audit record."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM execution_events WHERE at < ?", (float(older_than),))
            return int(cursor.rowcount)

    def events(self, execution_id: str, after: int = 0) -> List[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT seq,event,at,payload FROM execution_events WHERE execution_id=? AND seq>? ORDER BY seq",
                (execution_id, after),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload"] or "{}")
            result.append({"seq": row["seq"], "event": row["event"], "at": row["at"], **payload})
        return result

    def completed_with_workspace(self) -> List[ExecutionRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM executions WHERE status=? AND workspace IS NOT NULL "
                "ORDER BY updated_at DESC",
                (ExecutionStatus.COMPLETED.value,),
            ).fetchall()
        return [ExecutionRecord(**dict(row)) for row in rows]

    def recover_interrupted(self, lease_seconds: float = 30.0) -> int:
        """Requeue only work whose execution lease has expired.

        A durable queue must not blindly requeue every RUNNING job on process
        start: another worker may still own it. Lease expiry makes recovery
        safe across process crashes while allowing active workers to retain work.
        """
        now = time.time()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE executions
                   SET status=?, updated_at=?, lease_until=NULL, lease_owner=NULL
                 WHERE status IN (?, ?)
                   AND (lease_until IS NULL OR lease_until <= ?)""",
                (ExecutionStatus.QUEUED.value, now, ExecutionStatus.RUNNING.value, ExecutionStatus.VERIFYING.value, now),
            )
            return cur.rowcount

    def requeue_expired(self) -> int:
        return self.recover_interrupted()

    def pause_stale_capacity(self, min_resume_count: int = 1) -> List[str]:
        """Release stale capacity-blocked executions left active by older runtimes.

        This is intentionally conservative: it only touches active rows that already
        carry a provider/network/capacity error and have been resumed at least once.
        Startup is the recovery boundary; no worker from the previous process can
        legitimately continue owning these rows.
        """
        active = (
            ExecutionStatus.QUEUED.value,
            ExecutionStatus.RUNNING.value,
            ExecutionStatus.VERIFYING.value,
            ExecutionStatus.LEGACY_WAITING_CAPACITY.value,
        )
        tokens = (
            "provider_capacity", "connection refused", "urlopen", "network",
            "timeout", "timed out", "unavailable", "no eligible",
        )
        changed: List[str] = []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT execution_id,status,error,resume_count FROM executions "
                "WHERE status IN (?, ?, ?, ?)",
                active,
            ).fetchall()
            now = time.time()
            for row in rows:
                error = str(row["error"] or "").lower()
                if str(row["status"]) != ExecutionStatus.LEGACY_WAITING_CAPACITY.value:
                    if int(row["resume_count"] or 0) < int(min_resume_count):
                        continue
                    if not any(token in error for token in tokens):
                        continue
                conn.execute(
                    "UPDATE executions SET status=?, updated_at=?, lease_until=NULL, lease_owner=NULL "
                    "WHERE execution_id=?",
                    (ExecutionStatus.PAUSED_CAPACITY.value, now, row["execution_id"]),
                )
                changed.append(str(row["execution_id"]))
        return changed

    def list_queued(self, tenant_id: Optional[str] = None) -> List[ExecutionRecord]:
        with self._connection() as conn:
            if tenant_id is None:
                rows = conn.execute(
                    "SELECT * FROM executions WHERE status=? AND (lease_until IS NULL OR lease_until <= ?) ORDER BY created_at",
                    (ExecutionStatus.QUEUED.value, time.time()),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM executions WHERE status=? AND tenant_id=? AND (lease_until IS NULL OR lease_until <= ?) ORDER BY created_at",
                    (ExecutionStatus.QUEUED.value, tenant_id, time.time()),
                ).fetchall()
        return [ExecutionRecord(**dict(r)) for r in rows]

    def project_is_busy(self, project_id: str, tenant_id: str = "local") -> bool:
        active = (
            ExecutionStatus.QUEUED.value,
            ExecutionStatus.RUNNING.value,
            ExecutionStatus.VERIFYING.value,
            ExecutionStatus.WAITING_DECISION.value,
        )
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM executions WHERE project_id=? AND tenant_id=? AND status IN (?, ?, ?, ?) LIMIT 1",
                (project_id, tenant_id, *active),
            ).fetchone()
        return row is not None

    def claim(self, worker_id: str, lease_seconds: float = 30.0) -> Optional[ExecutionRecord]:
        """Atomically claim the oldest queued execution for one worker."""
        now = time.time()
        lease_until = now + float(lease_seconds)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE status=? AND (lease_until IS NULL OR lease_until <= ?) ORDER BY created_at LIMIT 1",
                (ExecutionStatus.QUEUED.value, now),
            ).fetchone()
            if row is None:
                return None
            execution_id = row["execution_id"]
            cur = conn.execute(
                """UPDATE executions
                      SET status=?, updated_at=?, lease_until=?, lease_owner=?, attempt_count=attempt_count+1
                    WHERE execution_id=?
                      AND status=?
                      AND (lease_until IS NULL OR lease_until <= ?)""",
                (ExecutionStatus.RUNNING.value, now, lease_until, worker_id, execution_id, ExecutionStatus.QUEUED.value, now),
            )
            if cur.rowcount != 1:
                return None
            claimed = conn.execute("SELECT * FROM executions WHERE execution_id=?", (execution_id,)).fetchone()
        return ExecutionRecord(**dict(claimed)) if claimed else None

    def renew_lease(self, execution_id: str, lease_seconds: float = 30.0, worker_id: Optional[str] = None) -> bool:
        now = time.time()
        lease_until = now + float(lease_seconds)
        with self._lock, self._connect() as conn:
            owner_clause = " AND lease_owner=?" if worker_id else ""
            values = [lease_until, now, execution_id, ExecutionStatus.RUNNING.value, ExecutionStatus.VERIFYING.value]
            if worker_id:
                values.append(worker_id)
            cur = conn.execute(
                "UPDATE executions SET lease_until=?, updated_at=? WHERE execution_id=? AND status IN (?, ?)" + owner_clause,
                values,
            )
            return cur.rowcount == 1

    def requeue(self, execution_id: str, error: Optional[str] = None, worker_id: Optional[str] = None) -> bool:
        fields = {"status": ExecutionStatus.QUEUED.value, "lease_until": None, "lease_owner": None}
        if error is not None:
            fields["error"] = error
        if worker_id is None:
            self.update(execution_id, **fields)
            return True
        assignments = ", ".join("%s=?" % key for key in fields)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE executions SET %s, updated_at=? WHERE execution_id=? AND lease_owner=?" % assignments,
                list(fields.values()) + [time.time(), execution_id, worker_id],
            )
            return cur.rowcount == 1

    def update_owned(self, execution_id: str, worker_id: str, statuses, **fields) -> bool:
        """Update only while this worker still owns the active lease."""
        if not fields:
            return False
        fields["updated_at"] = time.time()
        assignments = ", ".join("%s=?" % key for key in fields)
        values = list(fields.values()) + [execution_id, worker_id, *tuple(statuses)]
        placeholders = ", ".join("?" for _ in statuses)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE executions SET %s WHERE execution_id=? AND lease_owner=? AND status IN (%s)" % (assignments, placeholders),
                values,
            )
            return cur.rowcount == 1


class CloudRuntime:
    """Persistent asynchronous execution boundary for Web/mobile clients.

    The runtime persists the job lifecycle, creates one disposable workspace per
    execution and keeps the web request independent from model execution time.
    A process restart recovers RUNNING/VERIFYING jobs to QUEUED so the worker can
    safely replay the mission using Mission Resume semantics.
    """

    def __init__(self, data_dir: str, runner_factory: Callable[[str, Callable[[dict], None]], object], max_workers: int = 2, lease_seconds: float = 30.0, max_worker_retries: int = 3, memory_store=None, verifier_factory=None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root = self.data_dir / "workspaces"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.store = _Store(str(self.data_dir / "cloud_runtime.sqlite3"))
        self.projects = ProjectWorkspaceManager(str(self.data_dir))
        self.versions = ProjectVersionStore(self.projects, self.data_dir / "versions")
        self.decisions = DecisionStore(str(self.data_dir / "decisions.sqlite3"))
        self.runner_factory = runner_factory
        self.verifier_factory = verifier_factory or AgentVerifier
        self.max_workers = max(1, int(max_workers))
        self.lease_seconds = max(5.0, float(lease_seconds))
        self.max_worker_retries = max(0, int(max_worker_retries))
        try:
            self.max_capacity_resumes = max(0, int(os.environ.get("OLYMPUS_MAX_CAPACITY_RESUMES", "0")))
        except (TypeError, ValueError):
            self.max_capacity_resumes = 1
        try:
            self.capacity_retry_seconds = max(1.0, float(os.environ.get("OLYMPUS_CAPACITY_RETRY_SECONDS", "60")))
        except (TypeError, ValueError):
            self.capacity_retry_seconds = 60.0
        self.memory_context = MemoryContextProvider(memory_store) if memory_store is not None else None
        self.memory_writer = MemoryWriter(memory_store) if memory_store is not None else None
        self.worker_id = uuid.uuid4().hex[:12]
        self._lock = Lock()
        self._project_operations = RLock()
        self._active: Dict[str, Thread] = {}
        self._cancel: Dict[str, Event] = {}
        self._publish_hooks: List[Callable[[ExecutionRecord, object], object]] = []
        self._closed = False
        try:
            retention_days = max(1, int(os.environ.get("OLYMPUS_EVENT_RETENTION_DAYS", "30")))
        except (TypeError, ValueError):
            retention_days = 30
        self.store.prune_events(time.time() - retention_days * 86400)
        self._recover_legacy_completed_outputs()
        recovered_capacity = self.store.pause_stale_capacity(self.max_capacity_resumes)
        for execution_id in recovered_capacity:
            self.store.event(
                execution_id,
                "capacity_paused",
                reason="stale_capacity_lock_recovered",
                workspace_preserved=True,
            )
        self.store.recover_interrupted(self.lease_seconds)
        self._drain_queue()

    def _recover_legacy_completed_outputs(self) -> None:
        """Promote output stranded by releases that trusted an empty report."""
        for rec in self.store.completed_with_workspace():
            try:
                changes = self.projects.discover_execution_changes(
                    rec.project_id, rec.execution_id, tenant_id=rec.tenant_id
                )
                html_changes = tuple(path for path in changes if Path(path).suffix.lower() in {".html", ".htm"})
                task_text = str(rec.task or "").lower()
                web_requested = any(token in task_text for token in (
                    "landing page", "página", "pagina", "site", "website",
                    "interface web", "frontend", "html",
                ))
                if not changes or (web_requested and not html_changes):
                    continue
                verifier = AgentVerifier(str(Path(rec.workspace))) if rec.workspace else None
                verification = verifier.verify(changes) if verifier else None
                # Legacy records predate the quality contract.  They still
                # require independent syntax/integrity verification, but are
                # not re-evaluated against today's wording heuristics.
                if verification is None or not verification.passed:
                    continue
                promoted, before, after = self.versions.publish_execution(
                    rec.project_id,
                    rec.execution_id,
                    list(changes),
                    tenant_id=rec.tenant_id,
                )
                self.store.event(
                    rec.execution_id,
                    "legacy_result_recovered",
                    files=list(promoted),
                    previous_version_id=before.version_id,
                    version_id=after.version_id,
                )
            except (KeyError, OSError, ValueError):
                # Startup must remain available even if an old execution was
                # manually removed or its workspace is incomplete.
                continue

    def add_publish_hook(self, hook: Callable[[ExecutionRecord, object], object]) -> None:
        """Register a post-publication integration.

        Hooks are optional by default: failures are recorded while the local
        verified result remains usable. A hook marked ``required = True`` is
        part of the delivery contract and makes the mission ``blocked`` until
        the external publication succeeds.
        """
        with self._lock:
            if hook not in self._publish_hooks:
                self._publish_hooks.append(hook)

    def submit(self, project_id: str, task: str, max_iterations: int = 12, project_name: Optional[str] = None, tenant_id: str = "local", user_id: str = "local", execution_policy: Optional[dict] = None) -> ExecutionRecord:
        with self._project_operations:
            self.projects.ensure(project_id, project_name, tenant_id=tenant_id)
            if self.project_is_busy(project_id, tenant_id):
                raise RuntimeError("project already has an active execution")
            mission_id = uuid.uuid4().hex[:12]
            rec = self.store.create(project_id, mission_id, task.strip(), max_iterations=max_iterations, tenant_id=tenant_id, user_id=user_id)
            workspace = self.projects.execution_workspace(project_id, rec.execution_id, tenant_id=tenant_id)
            workspace.mkdir(parents=True, exist_ok=True)
            if execution_policy:
                policy_path = workspace / ".olympus" / "execution-policy.json"
                policy_path.parent.mkdir(parents=True, exist_ok=True)
                policy_path.write_text(
                    json.dumps(execution_policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                try:
                    policy_path.chmod(0o600)
                except OSError:
                    pass
                self.store.event(
                    rec.execution_id,
                    "routing_policy_selected",
                    mode=str(execution_policy.get("mode") or "free_first"),
                    free_attempt_limit=int(execution_policy.get("free_attempt_limit") or 6),
                    paid_fallback_authorized=bool(execution_policy.get("paid_fallback_authorized")),
                    paid_attempt_limit=int(execution_policy.get("paid_attempt_limit") or 1),
                    paid_spend_cap_usd=float(execution_policy.get("paid_spend_cap_usd") or 0),
                )
            self.store.update(rec.execution_id, workspace=str(workspace))
        self._drain_queue()
        return self.store.get(rec.execution_id)  # type: ignore[return-value]

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        return self.store.get(execution_id)

    def list(self, tenant_id: str, limit: int = 100, project_id: Optional[str] = None, status: Optional[str] = None) -> List[ExecutionRecord]:
        return self.store.list(tenant_id, limit, project_id, status)

    def events(self, execution_id: str, after: int = 0) -> List[dict]:
        return self.store.events(execution_id, after)

    def project_is_busy(self, project_id: str, tenant_id: str = "local") -> bool:
        return self.store.project_is_busy(project_id, tenant_id)

    def restore_project_version(self, project_id: str, version_id: str, tenant_id: str = "local"):
        with self._project_operations:
            if self.project_is_busy(project_id, tenant_id):
                raise RuntimeError("project has an active execution")
            return self.versions.restore(project_id, version_id, tenant_id=tenant_id)

    def request_decision(self, execution_id: str, question: str, options: list, context: Optional[dict] = None, ttl_seconds: Optional[float] = None):
        rec = self.get(execution_id)
        if rec is None:
            raise KeyError("execution not found")
        if rec.status not in {ExecutionStatus.RUNNING.value, ExecutionStatus.VERIFYING.value, ExecutionStatus.QUEUED.value}:
            raise RuntimeError("execution cannot wait for decision")
        req = self.decisions.create(execution_id, rec.tenant_id, question, options, context, ttl_seconds)
        self.store.update(execution_id, status=ExecutionStatus.WAITING_DECISION.value, lease_until=None)
        self.store.event(execution_id, "decision_requested", decision_id=req.decision_id, question=req.question, options=req.options)
        return req

    def answer_decision(self, execution_id: str, decision_id: str, tenant_id: str, choice, comment: Optional[str] = None):
        rec = self.get(execution_id)
        if rec is None or rec.tenant_id != tenant_id:
            raise KeyError("execution not found")
        if rec.status != ExecutionStatus.WAITING_DECISION.value:
            raise RuntimeError("execution is not waiting for decision")
        req = self.decisions.get(decision_id, tenant_id)
        if req is None or req.execution_id != execution_id:
            raise KeyError("decision not found")
        answered = self.decisions.answer(decision_id, tenant_id, choice, comment)
        self.store.event(execution_id, "decision_answered", decision_id=decision_id, choice=choice, comment=comment)
        self.store.update(execution_id, status=ExecutionStatus.QUEUED.value, lease_until=None, error=None, resume_count=rec.resume_count + 1)
        self.store.event(execution_id, "resumed_after_decision", decision_id=decision_id)
        return answered

    def cancel(self, execution_id: str) -> bool:
        rec = self.store.get(execution_id)
        if rec is None or rec.status in {s.value for s in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.BLOCKED, ExecutionStatus.CANCELLED, ExecutionStatus.PAUSED_CAPACITY)}:
            return False
        token = self._cancel.get(execution_id)
        if token is not None:
            token.set()
        self.store.update(execution_id, status=ExecutionStatus.CANCELLED.value, error="cancelled by client")
        self.store.event(execution_id, "cancel_requested")
        return True

    def resume(self, execution_id: str) -> Optional[ExecutionRecord]:
        rec = self.store.get(execution_id)
        if rec is None:
            return None
        if rec.status not in {ExecutionStatus.CANCELLED.value, ExecutionStatus.BLOCKED.value, ExecutionStatus.FAILED.value, ExecutionStatus.PAUSED_CAPACITY.value}:
            return rec
        expanded_budget = rec.max_iterations
        if "iteration budget exhausted" in str(rec.error or "").lower():
            expanded_budget = max(rec.max_iterations, 24)
        self.store.update(
            execution_id,
            status=ExecutionStatus.QUEUED.value,
            error=None,
            resume_count=rec.resume_count + 1,
            max_iterations=expanded_budget,
        )
        self.store.event(
            execution_id,
            "resumed",
            resume_count=rec.resume_count + 1,
            max_iterations=expanded_budget,
        )
        self._drain_queue()
        return self.store.get(execution_id)

    def close(self) -> None:
        self._closed = True
        with self._lock:
            tokens = list(self._cancel.values())
            threads = list(self._active.values())
        for token in tokens:
            token.set()
        deadline = time.time() + 2.0
        for thread in threads:
            remaining = max(0.0, deadline - time.time())
            thread.join(remaining)

    def _drain_queue(self) -> None:
        if self._closed:
            return
        with self._lock:
            active = sum(1 for t in self._active.values() if t.is_alive())
            available = self.max_workers - active
        for _ in range(max(0, available)):
            rec = self.store.claim(self.worker_id, self.lease_seconds)
            if rec is None:
                break
            token = Event()
            with self._lock:
                self._cancel[rec.execution_id] = token
                thread = Thread(target=self._worker, args=(rec.execution_id, rec.max_iterations, token), daemon=True)
                self._active[rec.execution_id] = thread
                thread.start()

    @staticmethod
    def _is_capacity_error(error: Optional[str]) -> bool:
        value = str(error or "").lower()
        return any(token in value for token in (
            "provider_capacity", "connection refused", "urlopen", "network",
            "timeout", "timed out", "unavailable", "no eligible",
            "rate_limited", "rate limit", "cooling down", "cooldown",
            "capacity_circuit_open", "circuit_open",
        ))

    def _schedule_drain(self, delay_seconds: float) -> None:
        def delayed() -> None:
            if self._closed:
                return
            time.sleep(max(0.0, float(delay_seconds)))
            self._drain_queue()
        Thread(target=delayed, name="olympus-capacity-retry", daemon=True).start()

    def _worker(self, execution_id: str, max_iterations: int, cancel: Event) -> None:
        rec0 = self.store.get(execution_id)
        if rec0 is None:
            return
        workspace = Path(rec0.workspace) if rec0.workspace else self.projects.execution_workspace(rec0.project_id, execution_id, tenant_id=rec0.tenant_id)
        workspace.mkdir(parents=True, exist_ok=True)
        retryable_infra_failure = False
        failure_stage = "setup"
        lease_stop = Event()

        def heartbeat() -> None:
            interval = max(1.0, self.lease_seconds / 3.0)
            while not lease_stop.wait(interval):
                if not self.store.renew_lease(execution_id, self.lease_seconds, self.worker_id):
                    return

        heartbeat_thread = Thread(target=heartbeat, name="olympus-lease-heartbeat", daemon=True)
        heartbeat_thread.start()
        try:
            self.store.update(
                execution_id,
                workspace=str(workspace),
                lease_until=time.time() + self.lease_seconds,
            )
            self.store.event(execution_id, "running", isolated=True, worker_id=self.worker_id)
            rec = self.store.get(execution_id)
            if rec is None:
                return

            def telemetry(event: dict) -> None:
                if cancel.is_set():
                    return
                name = str(event.get("event", "runtime"))
                payload = {k: v for k, v in event.items() if k != "event"}
                self.store.event(execution_id, name, **payload)

            failure_stage = "runner_setup"
            # Derive authority from the persisted user task, before agent-written
            # files or model statements can influence the publication decision.
            compiled_mission = MissionCompiler().compile(rec.task)
            acceptance_contract = compile_contract(rec.task, workspace)
            acceptance_contract.prepare()
            acceptance_contract.before = snapshot(self.projects.project_root(rec.project_id, rec.tenant_id))
            runner = self.runner_factory(str(workspace), telemetry)
            if cancel.is_set():
                return
            mission_task = rec.task
            if self.memory_context is not None:
                context = self.memory_context.relevant(rec.task, rec.tenant_id, rec.user_id, rec.project_id)
                if context:
                    mission_task = (
                        "CONTEXTO CONFIRMADO DO PROJETO (use somente quando relevante):\n"
                        + context
                        + "\n\nOBJETIVO ORIGINAL DA MISSÃO:\n"
                        + rec.task
                    )
                    self.store.event(execution_id, "memory_context_loaded", characters=len(context))
            failure_stage = "execution"
            result = runner.run(mission_task, max_iterations=max_iterations, resume=True)
            if cancel.is_set():
                return
            status = getattr(result, "status", "failed")
            if hasattr(status, "value"):
                status = status.value
            completion_error = None
            external_publication_failed = False
            if str(status) == ExecutionStatus.COMPLETED.value:
                failure_stage = "verification"
                self.store.update(execution_id, status=ExecutionStatus.VERIFYING.value)
                self.store.event(execution_id, "verification_started")
                reported_files = tuple(getattr(result, "files_modified", ()) or ())
                discovered_files = self.projects.discover_execution_changes(
                    rec.project_id, execution_id, tenant_id=rec.tenant_id
                )
                files_modified = list(dict.fromkeys(reported_files + discovered_files))
                tests_run = tuple(getattr(result, "tests_run", ()) or ())
                verification_error = None
                try:
                    verifier = self.verifier_factory(str(workspace))
                    acceptance_results, _ = acceptance_contract.verify(files_modified)
                    acceptance_errors = tuple(
                        "acceptance: " + line for line in format_failures(acceptance_results).splitlines()
                    )
                    verification = verifier.verify(files_modified, tests_run)
                    # Executable checks may change the output. Capture/review
                    # the final bytes, never a page from before those checks.
                    quality_errors = verifier.verify_task_deliverable(
                        compiled_mission.instruction(), files_modified,
                        compiled_mission.required_skills + compiled_mission.supporting_skills,
                    )
                    verification_error = tuple(dict.fromkeys(quality_errors + verification.errors + acceptance_errors))
                except (OSError, ValueError, TypeError) as exc:
                    verification = None
                    verification_error = ("independent verification could not inspect the workspace: %s" % exc,)
                if not files_modified:
                    status = ExecutionStatus.FAILED.value
                    completion_error = (
                        "completion_validation: no deliverable files were produced; "
                        "the mission was not published"
                    )
                    self.store.event(
                        execution_id,
                        "completion_rejected",
                        reason="no_deliverable_files",
                    )
                elif verification is None or not verification.passed or verification_error:
                    status = ExecutionStatus.FAILED.value
                    completion_error = "completion_validation: independent verification failed; the mission was not published"
                    self.store.event(
                        execution_id,
                        "completion_rejected",
                        reason="independent_verification_failed",
                        errors=list(verification_error or ("verification failed",))[:20],
                        delivery_review=getattr(verifier, "delivery_review", None),
                        verification=verification.report.to_dict() if verification is not None else None,
                    )
                else:
                    failure_stage = "publication"
                    promoted, previous_version, published_version = self.versions.publish_execution(
                        rec.project_id,
                        execution_id,
                        files_modified,
                        tenant_id=rec.tenant_id,
                    )
                    self.store.event(
                        execution_id,
                        "result_published",
                        files=list(promoted),
                        delivery_review=verifier.delivery_review,
                        verification=verification.report.to_dict(),
                        acceptance=[item.line() for item in acceptance_results],
                        contract_sha256=compiled_mission.original_sha256,
                        files_recovered=list(
                            path for path in discovered_files if path not in reported_files
                        ),
                        previous_version_id=previous_version.version_id,
                        version_id=published_version.version_id,
                    )
                    with self._lock:
                        publish_hooks = tuple(self._publish_hooks)
                    for hook in publish_hooks:
                        try:
                            integration_result = hook(rec, published_version)
                            if integration_result is not None:
                                self.store.event(execution_id, "integration_synced", integration="github")
                        except Exception as integration_error:
                            if bool(getattr(hook, "required", False)):
                                external_publication_failed = True
                            self.store.event(
                                execution_id,
                                "integration_failed",
                                integration="github",
                                error="A sincronização externa não foi concluída; a entrega local permanece válida.",
                                error_type=type(integration_error).__name__[:100],
                            )
            if external_publication_failed:
                status = ExecutionStatus.BLOCKED.value
                completion_error = "external_publication_failed: a missão local foi preservada, mas a publicação externa obrigatória não foi concluída"
                self.store.event(execution_id, "completion_rejected", reason="external_publication_failed")

            result_error = completion_error or getattr(result, "error", None)
            if str(status) == ExecutionStatus.BLOCKED.value and self._is_capacity_error(result_error):
                current = self.store.get(execution_id)
                resume_count = int(current.resume_count if current is not None else 0)
                if resume_count < self.max_capacity_resumes:
                    retry_at = time.time() + self.capacity_retry_seconds
                    requeued = self.store.update_owned(
                        execution_id,
                        self.worker_id,
                        (ExecutionStatus.RUNNING.value, ExecutionStatus.VERIFYING.value),
                        status=ExecutionStatus.QUEUED.value,
                        error=result_error,
                        resume_count=resume_count + 1,
                        lease_until=retry_at,
                        lease_owner=None,
                    )
                    if requeued:
                        self.store.event(
                            execution_id,
                            "waiting_for_capacity",
                            reason="provider_capacity_unavailable",
                            retry_in_seconds=int(self.capacity_retry_seconds),
                            resume_count=resume_count + 1,
                            checkpoint_preserved=True,
                            workspace_preserved=True,
                        )
                        self._schedule_drain(self.capacity_retry_seconds)
                        return
                status = ExecutionStatus.PAUSED_CAPACITY.value
                completion_error = str(result_error or "provider_capacity_unavailable")
                self.store.event(
                    execution_id,
                    "capacity_paused",
                    reason="capacity_retry_limit_reached",
                    resume_count=resume_count,
                    workspace_preserved=True,
                )

            final_updated = self.store.update_owned(
                execution_id,
                self.worker_id,
                (ExecutionStatus.RUNNING.value, ExecutionStatus.VERIFYING.value),
                status=str(status),
                result_summary=json.dumps(asdict(result) if hasattr(result, "__dataclass_fields__") else str(result), ensure_ascii=False, default=str),
                error=completion_error or getattr(result, "error", None),
                lease_until=None,
                lease_owner=None,
            )
            if not final_updated:
                self.store.event(execution_id, "stale_worker_result_discarded", worker_id=self.worker_id)
                return
            if self.memory_writer is not None and str(status) == ExecutionStatus.COMPLETED.value:
                try:
                    self.memory_writer.propose(
                        rec.tenant_id,
                        rec.user_id,
                        MemoryType.DECISION,
                        "mission:%s" % execution_id,
                        {
                            "project_id": rec.project_id,
                            "execution_id": execution_id,
                            "task": rec.task[:2000],
                            "status": str(status),
                            "files_modified": list(getattr(result, "files_modified", ()) or ())[:100],
                        },
                        sensitivity=Sensitivity.MEDIUM,
                        project_id=rec.project_id,
                        source="mission",
                    )
                    self.store.event(execution_id, "memory_context_saved", status="proposed")
                except (OSError, PermissionError, ValueError, TypeError):
                    self.store.event(execution_id, "memory_save_skipped")
            self.store.event(execution_id, "completed" if status == "completed" else "finished", status=str(status))
        except Exception as exc:
            rec = self.store.get(execution_id)
            attempts = rec.attempt_count if rec is not None else self.max_worker_retries + 1
            # Frame locations only: no source lines, locals or exception values.
            trace = [{"file": Path(frame.filename).name[:160], "line": frame.lineno,
                      "function": frame.name[:160]}
                     for frame in traceback.extract_tb(exc.__traceback__, limit=30)]
            diagnostic = {"failure_stage": failure_stage,
                          "error_type": type(exc).__name__[:100], "traceback": trace}
            if attempts <= self.max_worker_retries and not cancel.is_set():
                retryable_infra_failure = True
                # Keep the workspace so MissionCheckpointStore can resume safely.
                self.store.requeue(execution_id, error=str(exc), worker_id=self.worker_id)
                self.store.event(execution_id, "worker_requeued", attempt=attempts, error=str(exc), workspace_preserved=True, **diagnostic)
            else:
                self.store.update_owned(
                    execution_id,
                    self.worker_id,
                    (ExecutionStatus.RUNNING.value, ExecutionStatus.VERIFYING.value),
                    status=ExecutionStatus.FAILED.value,
                    error=str(exc),
                    lease_until=None,
                    lease_owner=None,
                )
                self.store.event(execution_id, "failed", error=str(exc), **diagnostic)
        finally:
            lease_stop.set()
            heartbeat_thread.join(timeout=1.0)
            if not retryable_infra_failure:
                # Project execution workspaces are retained for mission resume,
                # audit and cross-device history. Cleanup is an explicit policy.
                pass
            with self._lock:
                self._active.pop(execution_id, None)
                self._cancel.pop(execution_id, None)
            self._drain_queue()
