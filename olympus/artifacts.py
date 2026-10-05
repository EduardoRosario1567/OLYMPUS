from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import closing
import hashlib, json, mimetypes, os, sqlite3, time, uuid

class ArtifactType(str, Enum):
    CODE='code'; DOCUMENT='document'; SPREADSHEET='spreadsheet'; PRESENTATION='presentation'; PAGE='page'; IMAGE='image'; DATA='data'; OTHER='other'

@dataclass(frozen=True)
class Artifact:
    id: str; tenant_id: str; project_id: str; mission_id: str; execution_id: str
    type: ArtifactType; name: str; storage_path: str; size_bytes: int; version: int
    metadata: Dict[str, Any]; sha256: str; created_at: float

class ArtifactStore:
    def __init__(self, db_path: str, storage_root: str):
        self.db_path=str(Path(db_path)); self.storage_root=Path(storage_root).resolve(); self.storage_root.mkdir(parents=True,exist_ok=True); self._init()
    def _conn(self):
        c=sqlite3.connect(self.db_path); c.row_factory=sqlite3.Row; return c
    def _init(self):
        with closing(self._conn()) as c:
            c.execute('''CREATE TABLE IF NOT EXISTS artifacts(
              id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, mission_id TEXT NOT NULL,
              execution_id TEXT NOT NULL, type TEXT NOT NULL, name TEXT NOT NULL, storage_path TEXT NOT NULL,
              size_bytes INTEGER NOT NULL, version INTEGER NOT NULL, metadata_json TEXT NOT NULL,
              sha256 TEXT NOT NULL, created_at REAL NOT NULL)''')
            c.execute('CREATE INDEX IF NOT EXISTS idx_art_scope ON artifacts(tenant_id,project_id,mission_id,created_at)')
            c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_art_version ON artifacts(tenant_id,project_id,mission_id,name,version)')
            c.commit()
    @staticmethod
    def _safe_name(name:str)->str:
        clean=Path(name).name.strip()
        if not clean or clean in {'.','..'}: raise ValueError('invalid artifact name')
        return clean
    def create(self, tenant_id:str, project_id:str, mission_id:str, execution_id:str, type:ArtifactType, name:str, content:bytes, metadata:Optional[Dict[str,Any]]=None)->Artifact:
        name=self._safe_name(name); content=bytes(content); now=time.time()
        with closing(self._conn()) as c:
            row=c.execute('SELECT COALESCE(MAX(version),0) AS v FROM artifacts WHERE tenant_id=? AND project_id=? AND mission_id=? AND name=?',(tenant_id,project_id,mission_id,name)).fetchone()
            version=int(row['v'])+1
        aid=str(uuid.uuid4()); directory=self.storage_root/tenant_id/project_id/mission_id/aid; directory.mkdir(parents=True,exist_ok=False)
        target=(directory/name).resolve()
        if self.storage_root not in target.parents: raise PermissionError('artifact path escaped storage root')
        tmp=target.with_suffix(target.suffix+'.tmp'); tmp.write_bytes(content); os.replace(str(tmp),str(target))
        digest=hashlib.sha256(content).hexdigest(); meta=dict(metadata or {}); meta.setdefault('content_type',mimetypes.guess_type(name)[0] or 'application/octet-stream')
        art=Artifact(aid,tenant_id,project_id,mission_id,execution_id,type,name,str(target.relative_to(self.storage_root)),len(content),version,meta,digest,now)
        with closing(self._conn()) as c:
            c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(art.id,art.tenant_id,art.project_id,art.mission_id,art.execution_id,art.type.value,art.name,art.storage_path,art.size_bytes,art.version,json.dumps(art.metadata,ensure_ascii=False),art.sha256,art.created_at)); c.commit()
        return art
    def get(self, artifact_id:str, tenant_id:str)->Optional[Artifact]:
        with closing(self._conn()) as c: r=c.execute('SELECT * FROM artifacts WHERE id=? AND tenant_id=?',(artifact_id,tenant_id)).fetchone()
        return self._row(r) if r else None
    def list(self, tenant_id:str, project_id:Optional[str]=None, mission_id:Optional[str]=None)->List[Artifact]:
        q='SELECT * FROM artifacts WHERE tenant_id=?'; a=[tenant_id]
        if project_id is not None: q+=' AND project_id=?'; a.append(project_id)
        if mission_id is not None: q+=' AND mission_id=?'; a.append(mission_id)
        q+=' ORDER BY created_at DESC'
        with closing(self._conn()) as c: rows=c.execute(q,a).fetchall()
        return [self._row(r) for r in rows]
    def content_path(self, artifact_id:str, tenant_id:str)->Optional[Path]:
        art=self.get(artifact_id,tenant_id)
        if not art:return None
        p=(self.storage_root/art.storage_path).resolve()
        if self.storage_root not in p.parents:return None
        return p if p.is_file() else None
    def delete(self, artifact_id:str, tenant_id:str)->bool:
        art=self.get(artifact_id,tenant_id)
        if not art:return False
        p=self.content_path(artifact_id,tenant_id)
        with closing(self._conn()) as c: cur=c.execute('DELETE FROM artifacts WHERE id=? AND tenant_id=?',(artifact_id,tenant_id)); c.commit()
        if p:
            try:p.unlink(); p.parent.rmdir()
            except OSError:pass
        return cur.rowcount>0
    @staticmethod
    def _row(r):
        return Artifact(r['id'],r['tenant_id'],r['project_id'],r['mission_id'],r['execution_id'],ArtifactType(r['type']),r['name'],r['storage_path'],r['size_bytes'],r['version'],json.loads(r['metadata_json']),r['sha256'],r['created_at'])

def artifact_evidence(store:ArtifactStore, artifact_id:str, tenant_id:str):
    from olympus.agent.verification_engine import CheckStatus, VerificationCheck, VerificationEvidence
    art=store.get(artifact_id,tenant_id); p=store.content_path(artifact_id,tenant_id)
    if not art or not p:
        return VerificationCheck('artifact:%s'%artifact_id,CheckStatus.FAIL,(VerificationEvidence('artifact','expected artifact is missing'),),required=True)
    data=p.read_bytes(); digest=hashlib.sha256(data).hexdigest(); ok=len(data)==art.size_bytes and digest==art.sha256
    return VerificationCheck('artifact:%s'%artifact_id,CheckStatus.PASS if ok else CheckStatus.FAIL,(VerificationEvidence('artifact','artifact exists and integrity matches' if ok else 'artifact integrity mismatch',{'name':art.name,'version':art.version,'sha256':digest}),),required=True)
