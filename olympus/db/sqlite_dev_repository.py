"""
Implementação SQLite do RepositorioPersistencia — só para desenvolvimento
local e testes, sem depender de SQLAlchemy nem de um Postgres real.
Cumpre exatamente o mesmo contrato que PostgresRepository (db/repository.py),
então o pipeline funciona idêntico nos dois backends.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
import atexit
import weakref
from typing import Optional

DDL = """
CREATE TABLE IF NOT EXISTS projetos (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    product_type TEXT,
    complexity TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execucoes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projetos(id),
    status TEXT NOT NULL DEFAULT 'pending',
    total_cost REAL NOT NULL DEFAULT 0,
    total_latency_ms INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    fallback_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    result_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisao_registros (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projetos(id),
    task_id TEXT,
    execution_id TEXT REFERENCES execucoes(id),
    input_type TEXT NOT NULL,
    task_description TEXT NOT NULL,
    selected_provider TEXT NOT NULL,
    selected_model TEXT NOT NULL,
    candidate_models TEXT NOT NULL DEFAULT '[]',
    policy_applied TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    confidence_score REAL NOT NULL DEFAULT 0,
    estimated_cost REAL NOT NULL DEFAULT 0,
    estimated_latency_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'approved',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projetos(id),
    execution_id TEXT REFERENCES execucoes(id),
    decision_record_id TEXT REFERENCES decisao_registros(id),
    level TEXT NOT NULL DEFAULT 'info',
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_results (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES execucoes(id),
    decision_record_id TEXT NOT NULL REFERENCES decisao_registros(id),
    requested_model TEXT NOT NULL,
    actual_model TEXT NOT NULL,
    provider TEXT NOT NULL,
    output TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    status TEXT NOT NULL DEFAULT 'success' CHECK (
        status IN ('success','timeout','provider_error','billing_error',
                   'unavailable','rate_limited','authentication_error',
                   'malformed_response','unknown_error')
    ),
    correlation_id TEXT,
    usage TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_results_execution_id ON execution_results(execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_results_decision_record_id ON execution_results(decision_record_id);
CREATE INDEX IF NOT EXISTS idx_execution_results_created_at ON execution_results(created_at);

CREATE TABLE IF NOT EXISTS quality_evaluations (
    id TEXT PRIMARY KEY,
    execution_result_id TEXT NOT NULL REFERENCES execution_results(id),
    quality_score REAL NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    passed INTEGER NOT NULL DEFAULT 0,
    evaluator TEXT NOT NULL,
    reason TEXT NOT NULL,
    criteria TEXT NOT NULL DEFAULT '{}',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_evaluations_execution_result_id ON quality_evaluations(execution_result_id);
CREATE INDEX IF NOT EXISTS idx_quality_evaluations_created_at ON quality_evaluations(created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_LIVE_REPOSITORIES = weakref.WeakSet()


def _close_live_repositories() -> None:
    for repo in list(_LIVE_REPOSITORIES):
        try:
            repo.close()
        except Exception:
            pass


atexit.register(_close_live_repositories)


class SQLiteDevRepository:
    """Cumpre RepositorioPersistencia (db/interfaces.py) usando sqlite3 puro."""

    def __init__(self, path: str = ":memory:") -> None:
        # FastAPI executa endpoints síncronos em uma thread pool. O repositório
        # é compartilhado pelo runtime local, portanto a conexão precisa poder
        # ser usada pelas threads de requisição (SQLite continua serializando
        # o acesso internamente).
        self.conn = sqlite3.connect(path, check_same_thread=False)
        _LIVE_REPOSITORIES.add(self)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.executescript(DDL)

    def close(self) -> None:
        conn = getattr(self, "conn", None)
        if conn is not None:
            conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def criar_execucao(self, project_id: str) -> str:
        execucao_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO execucoes (id, project_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (execucao_id, project_id, "running", _now(), _now()),
        )
        return execucao_id

    def registrar_decisao(
        self,
        *,
        tarefa_id: str,
        modelo_escolhido: Optional[str],
        candidatos_avaliados: list[str],
        motivo: str,
        confianca: float,
        decisao_status: str,
        input_type: str,
        task_description: str,
        selected_provider: str,
        policy_applied: str,
        estimated_cost: float,
        estimated_latency_ms: int,
        project_id: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> str:
        decisao_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO decisao_registros
               (id, project_id, task_id, execution_id, input_type, task_description,
                selected_provider, selected_model, candidate_models, policy_applied,
                decision_reason, confidence_score, estimated_cost, estimated_latency_ms,
                status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                decisao_id, project_id, tarefa_id, execution_id, input_type, task_description,
                selected_provider, modelo_escolhido or "nenhum", json.dumps(candidatos_avaliados),
                policy_applied, motivo, confianca, estimated_cost, estimated_latency_ms,
                decisao_status, _now(), _now(),
            ),
        )
        return decisao_id

    def registrar_log(
        self,
        *,
        event_type: str,
        message: str,
        level: str = "info",
        project_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        decision_record_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        log_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO logs (id, project_id, execution_id, decision_record_id, level,
               event_type, message, metadata, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                log_id, project_id, execution_id, decision_record_id, level,
                event_type, message, json.dumps(metadata or {}), _now(),
            ),
        )
        return log_id

    def finalizar_execucao(
        self,
        execution_id: str,
        *,
        status: str,
        total_cost: float = 0,
        total_latency_ms: int = 0,
        success_count: int = 0,
        fallback_count: int = 0,
        error_message: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """UPDATE execucoes SET status=?, total_cost=?, total_latency_ms=?,
               success_count=?, fallback_count=?, error_message=?, result_summary=?, updated_at=?
               WHERE id=?""",
            (
                status, total_cost, total_latency_ms, success_count, fallback_count,
                error_message, result_summary, _now(), execution_id,
            ),
        )

    def commit(self) -> None:
        self.conn.commit()

    # ---- projetos ----

    def criar_projeto(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        product_type: Optional[str] = None,
        complexity: Optional[str] = None,
        status: str = "active",
    ) -> str:
        projeto_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO projetos (id, name, description, product_type, complexity, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (projeto_id, name, description, product_type, complexity, status, _now(), _now()),
        )
        return projeto_id

    def listar_projetos(self, limit: int = 50) -> list[dict]:
        cur = self.conn.execute(
            """SELECT id, name, description, product_type, complexity, status, created_at, updated_at
               FROM projetos ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        colunas = [d[0] for d in cur.description]
        return [dict(zip(colunas, row)) for row in cur.fetchall()]

    def obter_projeto(self, project_id: str) -> Optional[dict]:
        cur = self.conn.execute(
            """SELECT id, name, description, product_type, complexity, status, created_at, updated_at
               FROM projetos WHERE id = ?""",
            (project_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        colunas = [d[0] for d in cur.description]
        return dict(zip(colunas, row))

    # ---- execuções ----

    def listar_execucoes(
        self,
        limit: int = 50,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        condicoes, params = [], []
        if project_id is not None:
            condicoes.append("e.project_id = ?")
            params.append(project_id)
        if status is not None:
            condicoes.append("e.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

        cur = self.conn.execute(
            f"""SELECT e.id, e.project_id, e.status, e.total_cost, e.total_latency_ms,
                       e.success_count, e.fallback_count, e.created_at,
                       (SELECT d.selected_model FROM decisao_registros d
                        WHERE d.execution_id = e.id
                        GROUP BY d.selected_model ORDER BY COUNT(*) DESC LIMIT 1) AS modelo_principal,
                       (SELECT AVG(d.confidence_score) FROM decisao_registros d
                        WHERE d.execution_id = e.id) AS confianca_media
                FROM execucoes e
                {where}
                ORDER BY e.created_at DESC LIMIT ?""",
            (*params, limit),
        )
        colunas = [d[0] for d in cur.description]
        resultados = [dict(zip(colunas, row)) for row in cur.fetchall()]
        for r in resultados:
            r["fallback_usado"] = r["fallback_count"] > 0
        return resultados

    def obter_execucao(self, execution_id: str) -> Optional[dict]:
        cur = self.conn.execute(
            """SELECT e.id, e.project_id, e.status, e.total_cost, e.total_latency_ms,
                       e.success_count, e.fallback_count, e.created_at, e.result_summary
                FROM execucoes e WHERE e.id = ?""",
            (execution_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        colunas = [d[0] for d in cur.description]
        return dict(zip(colunas, row))

    def listar_execucoes_recentes(self, limit: int = 20) -> list[dict]:
        """Mantido por compatibilidade (usado pelo dashboard da Fase 2.1)."""
        return self.listar_execucoes(limit=limit)

    # ---- logs ----

    def listar_logs(
        self,
        limit: int = 50,
        project_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        level: Optional[str] = None,
        busca: Optional[str] = None,
    ) -> list[dict]:
        condicoes, params = [], []
        if project_id is not None:
            condicoes.append("project_id = ?")
            params.append(project_id)
        if execution_id is not None:
            condicoes.append("execution_id = ?")
            params.append(execution_id)
        if level is not None:
            condicoes.append("level = ?")
            params.append(level)
        if busca:
            condicoes.append("(message LIKE ? OR event_type LIKE ?)")
            params.extend([f"%{busca}%", f"%{busca}%"])
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

        cur = self.conn.execute(
            f"""SELECT id, project_id, execution_id, decision_record_id, level,
                       event_type, message, metadata, created_at
                FROM logs {where} ORDER BY created_at DESC LIMIT ?""",
            (*params, limit),
        )
        colunas = [d[0] for d in cur.description]
        return [dict(zip(colunas, row)) for row in cur.fetchall()]

    def listar_logs_recentes(self, limit: int = 20) -> list[dict]:
        """Mantido por compatibilidade (usado pelo dashboard da Fase 2.1)."""
        return self.listar_logs(limit=limit)

    def resumo_metricas(self) -> dict:
        cur = self.conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(total_cost),0), COALESCE(AVG(total_latency_ms),0),
                      COALESCE(SUM(success_count),0), COALESCE(SUM(fallback_count),0)
               FROM execucoes"""
        )
        total_execucoes, custo_total, latencia_media_ms, total_sucessos, total_fallbacks = cur.fetchone()

        cur2 = self.conn.execute("SELECT COUNT(*) FROM decisao_registros")
        total_decisoes = cur2.fetchone()[0]

        cur3 = self.conn.execute(
            "SELECT COUNT(*) FROM decisao_registros WHERE status IN ('fallback','downgraded')"
        )
        total_decisoes_com_desvio = cur3.fetchone()[0]

        cur4 = self.conn.execute(
            """SELECT selected_model, COUNT(*) as n FROM decisao_registros
               GROUP BY selected_model ORDER BY n DESC LIMIT 1"""
        )
        row4 = cur4.fetchone()
        modelo_mais_usado = row4[0] if row4 else None

        taxa_sucesso = (total_sucessos / total_decisoes) if total_decisoes else 0.0
        fallback_rate = (total_decisoes_com_desvio / total_decisoes) if total_decisoes else 0.0

        return {
            "total_execucoes": total_execucoes,
            "custo_total": custo_total,
            "latencia_media_ms": latencia_media_ms,
            "taxa_sucesso": taxa_sucesso,
            "fallback_rate": fallback_rate,
            "total_decisoes": total_decisoes,
            "total_decisoes_com_desvio": total_decisoes_com_desvio,
            "modelo_mais_usado": modelo_mais_usado,
        }

    # ---- execution_results (PATCH 004B) ----

    def registrar_execution_result(
        self,
        *,
        execution_id: str,
        decision_record_id: str,
        requested_model: str,
        actual_model: str,
        provider: str,
        output: str,
        latency_ms: int,
        cost: float,
        success: bool,
        error: Optional[str] = None,
        status: str = "success",
        correlation_id: Optional[str] = None,
        usage: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Persiste um resultado de execução real e retorna seu id."""
        result_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO execution_results
               (id, execution_id, decision_record_id, requested_model, actual_model,
                provider, output, latency_ms, cost, success, error, status,
                correlation_id, usage, metadata, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                result_id, execution_id, decision_record_id, requested_model, actual_model,
                provider, output, latency_ms, (0.0 if cost is None else cost),
                1 if success else 0, error, status,
                correlation_id, json.dumps(usage or {}), json.dumps(metadata or {}), _now(),
            ),
        )
        return result_id

    def obter_execution_result(self, result_id: str) -> Optional[dict]:
        """Obtém um resultado de execução por id."""
        cur = self.conn.execute(
            """SELECT id, execution_id, decision_record_id, requested_model, actual_model,
                      provider, output, latency_ms, cost, success, error, status,
                      correlation_id, usage, metadata, created_at
               FROM execution_results WHERE id = ?""",
            (result_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        colunas = [d[0] for d in cur.description]
        result = dict(zip(colunas, row))
        # Converter fields JSON
        if result["usage"]:
            result["usage"] = json.loads(result["usage"])
        if result["metadata"]:
            result["metadata"] = json.loads(result["metadata"])
        result["success"] = bool(result["success"])
        return result

    def obter_execution_result_por_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém o resultado de execução associado a um decision_record_id."""
        cur = self.conn.execute(
            """SELECT id, execution_id, decision_record_id, requested_model, actual_model,
                      provider, output, latency_ms, cost, success, error, status,
                      correlation_id, usage, metadata, created_at
               FROM execution_results WHERE decision_record_id = ?""",
            (decision_record_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        colunas = [d[0] for d in cur.description]
        result = dict(zip(colunas, row))
        if result["usage"]:
            result["usage"] = json.loads(result["usage"])
        if result["metadata"]:
            result["metadata"] = json.loads(result["metadata"])
        result["success"] = bool(result["success"])
        return result

    def obter_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém um registro de decisão por id."""
        cur = self.conn.execute(
            """SELECT id, project_id, task_id, execution_id, input_type, task_description,
                      selected_provider, selected_model, candidate_models, policy_applied,
                      decision_reason, confidence_score, estimated_cost, estimated_latency_ms,
                      status, created_at, updated_at
               FROM decisao_registros WHERE id = ?""",
            (decision_record_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        colunas = [d[0] for d in cur.description]
        result = dict(zip(colunas, row))
        if result["candidate_models"]:
            result["candidate_models"] = json.loads(result["candidate_models"])
        return result

    def listar_execution_results(
        self,
        limit: int = 50,
        execution_id: Optional[str] = None,
        decision_record_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista resultados de execução com filtros opcionais."""
        condicoes, params = [], []
        if execution_id is not None:
            condicoes.append("execution_id = ?")
            params.append(execution_id)
        if decision_record_id is not None:
            condicoes.append("decision_record_id = ?")
            params.append(decision_record_id)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

        cur = self.conn.execute(
            f"""SELECT id, execution_id, decision_record_id, requested_model, actual_model,
                       provider, output, latency_ms, cost, success, error, status,
                       correlation_id, usage, metadata, created_at
                FROM execution_results {where} ORDER BY created_at DESC LIMIT ?""",
            (*params, limit),
        )
        colunas = [d[0] for d in cur.description]
        resultados = []
        for row in cur.fetchall():
            result = dict(zip(colunas, row))
            if result["usage"]:
                result["usage"] = json.loads(result["usage"])
            if result["metadata"]:
                result["metadata"] = json.loads(result["metadata"])
            result["success"] = bool(result["success"])
            resultados.append(result)
        return resultados

    # ---- quality_evaluations (PATCH 005D) ----

    def registrar_quality_evaluation(
        self,
        *,
        execution_result_id: str,
        quality_score: float,
        passed: bool,
        evaluator: str,
        reason: str,
        criteria: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Persiste uma avaliação de qualidade e retorna seu id."""
        eval_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO quality_evaluations
               (id, execution_result_id, quality_score, passed, evaluator, reason,
                criteria, metadata, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                eval_id, execution_result_id, quality_score,
                1 if passed else 0, evaluator, reason,
                json.dumps(criteria or {}), json.dumps(metadata or {}), _now(),
            ),
        )
        return eval_id

    def obter_quality_evaluation(self, evaluation_id: str) -> Optional[dict]:
        """Obtém uma avaliação de qualidade por id."""
        cur = self.conn.execute(
            """SELECT id, execution_result_id, quality_score, passed, evaluator, reason,
                      criteria, metadata, created_at
               FROM quality_evaluations WHERE id = ?""",
            (evaluation_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        colunas = [d[0] for d in cur.description]
        result = dict(zip(colunas, row))
        if result["criteria"]:
            result["criteria"] = json.loads(result["criteria"])
        if result["metadata"]:
            result["metadata"] = json.loads(result["metadata"])
        result["passed"] = bool(result["passed"])
        return result

    def listar_quality_evaluations(
        self,
        limit: int = 50,
        execution_result_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista avaliações de qualidade com filtros opcionais."""
        condicoes, params = [], []
        if execution_result_id is not None:
            condicoes.append("execution_result_id = ?")
            params.append(execution_result_id)
        where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""

        cur = self.conn.execute(
            f"""SELECT id, execution_result_id, quality_score, passed, evaluator, reason,
                       criteria, metadata, created_at
                FROM quality_evaluations {where} ORDER BY created_at DESC LIMIT ?""",
            (*params, limit),
        )
        colunas = [d[0] for d in cur.description]
        resultados = []
        for row in cur.fetchall():
            result = dict(zip(colunas, row))
            if result["criteria"]:
                result["criteria"] = json.loads(result["criteria"])
            if result["metadata"]:
                result["metadata"] = json.loads(result["metadata"])
            result["passed"] = bool(result["passed"])
            resultados.append(result)
        return resultados
