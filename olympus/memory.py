from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import json, sqlite3, time, uuid
from contextlib import closing

class MemoryType(str, Enum):
    PERSONAL='personal'; PROJECT='project'; PREFERENCE='preference'; RULE='rule'; DECISION='decision'
class Sensitivity(str, Enum):
    LOW='low'; MEDIUM='medium'; HIGH='high'; NEVER_STORE='never_store'
class MemoryStatus(str, Enum):
    PROPOSED='proposed'; CONFIRMED='confirmed'; REJECTED='rejected'

@dataclass(frozen=True)
class Memory:
    id: str; tenant_id: str; user_id: str; project_id: Optional[str]; type: MemoryType; key: str
    value: Dict[str, Any]; sensitivity: Sensitivity; status: MemoryStatus; source: str
    created_at: float; updated_at: float

class MemoryPolicy:
    def desired_status(self, sensitivity: Sensitivity) -> MemoryStatus:
        if sensitivity == Sensitivity.NEVER_STORE:
            raise PermissionError('never_store memory cannot be persisted')
        return MemoryStatus.CONFIRMED if sensitivity == Sensitivity.LOW else MemoryStatus.PROPOSED

class MemoryStore:
    def __init__(self, path: str):
        self.path=str(Path(path)); self._init()
    def _conn(self):
        c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def _init(self):
        with closing(self._conn()) as c:
            c.execute('''CREATE TABLE IF NOT EXISTS memories(
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, project_id TEXT,
              type TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, sensitivity TEXT NOT NULL,
              status TEXT NOT NULL, source TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)''')
            c.execute('CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(tenant_id,user_id,project_id,type,status)'); c.commit()
    def put(self, memory: Memory) -> Memory:
        if memory.sensitivity == Sensitivity.NEVER_STORE: raise PermissionError('never_store memory cannot be persisted')
        with closing(self._conn()) as c:
            c.execute('INSERT OR REPLACE INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(
              memory.id,memory.tenant_id,memory.user_id,memory.project_id,memory.type.value,memory.key,
              json.dumps(memory.value,ensure_ascii=False),memory.sensitivity.value,memory.status.value,memory.source,
              memory.created_at,memory.updated_at)); c.commit()
        return memory
    def get(self, memory_id:str, tenant_id:str, user_id:str)->Optional[Memory]:
        with closing(self._conn()) as c: r=c.execute('SELECT * FROM memories WHERE id=? AND tenant_id=? AND user_id=?',(memory_id,tenant_id,user_id)).fetchone()
        return self._row(r) if r else None
    def list(self, tenant_id:str,user_id:str,project_id:Optional[str]=None,type:Optional[MemoryType]=None,confirmed_only:bool=False)->List[Memory]:
        q='SELECT * FROM memories WHERE tenant_id=? AND user_id=?'; a=[tenant_id,user_id]
        if project_id is not None: q+=' AND (project_id=? OR project_id IS NULL)'; a.append(project_id)
        if type is not None: q+=' AND type=?'; a.append(type.value)
        if confirmed_only: q+=' AND status=?'; a.append(MemoryStatus.CONFIRMED.value)
        q+=' ORDER BY updated_at DESC'
        with closing(self._conn()) as c: rows=c.execute(q,a).fetchall()
        return [self._row(r) for r in rows]
    def delete(self,memory_id:str,tenant_id:str,user_id:str)->bool:
        with closing(self._conn()) as c: cur=c.execute('DELETE FROM memories WHERE id=? AND tenant_id=? AND user_id=?',(memory_id,tenant_id,user_id)); c.commit(); return cur.rowcount>0
    def update(self,memory_id:str,tenant_id:str,user_id:str,**changes)->Optional[Memory]:
        m=self.get(memory_id,tenant_id,user_id)
        if not m:return None
        allowed={k:v for k,v in changes.items() if k in {'key','value','sensitivity','status'} and v is not None}
        if allowed.get('sensitivity')==Sensitivity.NEVER_STORE: self.delete(memory_id,tenant_id,user_id); return None
        return self.put(replace(m,updated_at=time.time(),**allowed))
    @staticmethod
    def _row(r):
        return Memory(r['id'],r['tenant_id'],r['user_id'],r['project_id'],MemoryType(r['type']),r['key'],json.loads(r['value_json']),Sensitivity(r['sensitivity']),MemoryStatus(r['status']),r['source'],r['created_at'],r['updated_at'])


class PostgresMemoryStore:
    """Cloud-backed memory store with the same contract as ``MemoryStore``.

    The driver is imported lazily so local development remains dependency-light.
    Values are stored as JSON text deliberately: this keeps migrations simple
    and works with the existing SQLite representation while preserving the
    tenant/user/project isolation predicates on every read and write.
    """
    def __init__(self, dsn: str):
        self.dsn = str(dsn).strip()
        if not self.dsn:
            raise ValueError("Postgres memory DSN is required")
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("psycopg2 is required for cloud memory storage") from exc
        self._psycopg2 = psycopg2
        self._init()

    def _conn(self):
        return self._psycopg2.connect(self.dsn)

    def _init(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS olympus_memories (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        project_id TEXT,
                        type TEXT NOT NULL,
                        memory_key TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        sensitivity TEXT NOT NULL,
                        status TEXT NOT NULL,
                        source TEXT NOT NULL,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_olympus_mem_scope
                    ON olympus_memories(tenant_id, user_id, project_id, type, status)
                """)

    def put(self, memory: Memory) -> Memory:
        if memory.sensitivity == Sensitivity.NEVER_STORE:
            raise PermissionError('never_store memory cannot be persisted')
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO olympus_memories
                    (id, tenant_id, user_id, project_id, type, memory_key, value_json,
                     sensitivity, status, source, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                      project_id=EXCLUDED.project_id, type=EXCLUDED.type,
                      memory_key=EXCLUDED.memory_key, value_json=EXCLUDED.value_json,
                      sensitivity=EXCLUDED.sensitivity, status=EXCLUDED.status,
                      source=EXCLUDED.source, updated_at=EXCLUDED.updated_at
                """, (memory.id, memory.tenant_id, memory.user_id, memory.project_id,
                       memory.type.value, memory.key, json.dumps(memory.value, ensure_ascii=False),
                       memory.sensitivity.value, memory.status.value, memory.source,
                       memory.created_at, memory.updated_at))
        return memory

    def get(self, memory_id: str, tenant_id: str, user_id: str) -> Optional[Memory]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id,tenant_id,user_id,project_id,type,memory_key,value_json,
                           sensitivity,status,source,created_at,updated_at
                    FROM olympus_memories
                    WHERE id=%s AND tenant_id=%s AND user_id=%s
                """, (memory_id, tenant_id, user_id))
                row = cur.fetchone()
        return self._row(row) if row else None

    def list(self, tenant_id: str, user_id: str, project_id: Optional[str] = None,
             type: Optional[MemoryType] = None, confirmed_only: bool = False) -> List[Memory]:
        clauses = ["tenant_id=%s", "user_id=%s"]
        args: list = [tenant_id, user_id]
        if project_id is not None:
            clauses.append("(project_id=%s OR project_id IS NULL)")
            args.append(project_id)
        if type is not None:
            clauses.append("type=%s")
            args.append(type.value)
        if confirmed_only:
            clauses.append("status=%s")
            args.append(MemoryStatus.CONFIRMED.value)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id,tenant_id,user_id,project_id,type,memory_key,value_json,
                           sensitivity,status,source,created_at,updated_at
                    FROM olympus_memories WHERE %s ORDER BY updated_at DESC
                """ % " AND ".join(clauses), args)
                rows = cur.fetchall()
        return [self._row(row) for row in rows]

    def delete(self, memory_id: str, tenant_id: str, user_id: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM olympus_memories WHERE id=%s AND tenant_id=%s AND user_id=%s", (memory_id, tenant_id, user_id))
                return cur.rowcount > 0

    def update(self, memory_id: str, tenant_id: str, user_id: str, **changes) -> Optional[Memory]:
        memory = self.get(memory_id, tenant_id, user_id)
        if not memory:
            return None
        allowed = {key: value for key, value in changes.items() if key in {'key', 'value', 'sensitivity', 'status'} and value is not None}
        if allowed.get('sensitivity') == Sensitivity.NEVER_STORE:
            self.delete(memory_id, tenant_id, user_id)
            return None
        return self.put(replace(memory, updated_at=time.time(), **allowed))

    @staticmethod
    def _row(row):
        return Memory(row[0], row[1], row[2], row[3], MemoryType(row[4]), row[5],
                      json.loads(row[6]), Sensitivity(row[7]), MemoryStatus(row[8]),
                      row[9], row[10], row[11])


def build_memory_store(location: Optional[str] = None):
    """Select cloud memory when a Postgres DSN is configured, else SQLite."""
    configured = str(location or '').strip()
    if configured.startswith(('postgres://', 'postgresql://')):
        return PostgresMemoryStore(configured)
    return MemoryStore(configured or ':memory:')

class MemoryWriter:
    def __init__(self,store:MemoryStore,policy:Optional[MemoryPolicy]=None): self.store=store; self.policy=policy or MemoryPolicy()
    def propose(self,tenant_id:str,user_id:str,type:MemoryType,key:str,value:Dict[str,Any],sensitivity:Sensitivity=Sensitivity.LOW,project_id:Optional[str]=None,source:str='mission')->Memory:
        status=self.policy.desired_status(sensitivity); now=time.time()
        return self.store.put(Memory(str(uuid.uuid4()),tenant_id,user_id,project_id,type,key,value,sensitivity,status,source,now,now))

class MemoryContextProvider:
    def __init__(self,store:MemoryStore,max_items:int=8,max_chars:int=2400): self.store=store; self.max_items=max_items; self.max_chars=max_chars
    def relevant(self,task:str,tenant_id:str,user_id:str,project_id:Optional[str]=None)->str:
        terms={x.lower() for x in task.split() if len(x)>2}; scored=[]
        for m in self.store.list(tenant_id,user_id,project_id,confirmed_only=True):
            text=(m.key+' '+json.dumps(m.value,ensure_ascii=False)).lower(); score=sum(1 for t in terms if t in text)
            if score or m.type in {MemoryType.RULE,MemoryType.PREFERENCE}: scored.append((score,m))
        scored.sort(key=lambda x:(x[0],x[1].updated_at),reverse=True)
        lines=[]
        for _,m in scored[:self.max_items]:
            line='[%s] %s = %s'%(m.type.value,m.key,json.dumps(m.value,ensure_ascii=False))
            if len('\n'.join(lines+[line]))>self.max_chars: break
            lines.append(line)
        return '\n'.join(lines)
