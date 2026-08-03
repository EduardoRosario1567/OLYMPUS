"""
Implementação Postgres/SQLAlchemy do RepositorioPersistencia.
Alvo de produção. Requer sqlalchemy + driver postgres (psycopg2/asyncpg)
instalados e uma conexão real — não executável neste sandbox (sem rede).
"""

from typing import Optional
from sqlalchemy.orm import Session

from olympus.db.interfaces import RepositorioPersistencia
from olympus.db import models as db


class PostgresRepository:
    """Implementa RepositorioPersistencia usando uma Session do SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def criar_execucao(self, project_id: str) -> str:
        execucao = db.Execucao(project_id=project_id, status=db.ExecutionStatus.RUNNING)
        self.session.add(execucao)
        self.session.flush()
        return str(execucao.id)

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
        registro = db.DecisaoRegistro(
            project_id=project_id,
            task_id=tarefa_id,
            execution_id=execution_id,
            input_type=input_type,
            task_description=task_description,
            selected_provider=selected_provider,
            selected_model=modelo_escolhido or "nenhum",
            candidate_models=candidatos_avaliados,
            policy_applied=policy_applied,
            decision_reason=motivo,
            confidence_score=confianca,
            estimated_cost=estimated_cost,
            estimated_latency_ms=estimated_latency_ms,
            status=db.DecisionStatus(decisao_status),
        )
        self.session.add(registro)
        self.session.flush()
        return str(registro.id)

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
        log = db.Log(
            project_id=project_id,
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            level=db.LogLevel(level),
            event_type=event_type,
            message=message,
            log_metadata=metadata or {},
        )
        self.session.add(log)
        self.session.flush()
        return str(log.id)

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
        execucao = self.session.get(db.Execucao, execution_id)
        if execucao is None:
            raise ValueError(f"Execução {execution_id} não encontrada.")
        execucao.status = db.ExecutionStatus(status)
        execucao.total_cost = total_cost
        execucao.total_latency_ms = total_latency_ms
        execucao.success_count = success_count
        execucao.fallback_count = fallback_count
        execucao.error_message = error_message
        execucao.result_summary = result_summary
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def listar_execucoes_recentes(self, limit: int = 20) -> list[dict]:
        execucoes = (
            self.session.query(db.Execucao)
            .order_by(db.Execucao.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": str(e.id),
                "project_id": str(e.project_id),
                "status": e.status.value,
                "total_cost": float(e.total_cost),
                "total_latency_ms": e.total_latency_ms,
                "success_count": e.success_count,
                "fallback_count": e.fallback_count,
                "created_at": e.created_at.isoformat(),
            }
            for e in execucoes
        ]

    def listar_logs_recentes(self, limit: int = 20) -> list[dict]:
        logs = (
            self.session.query(db.Log)
            .order_by(db.Log.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": str(l.id),
                "level": l.level.value,
                "event_type": l.event_type,
                "message": l.message,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ]

    def listar_execucoes_recentes(self, limit: int = 20) -> list[dict]:
        """Mantido por compatibilidade (usado pelo dashboard da Fase 2.1)."""
        return self.listar_execucoes(limit=limit)

    def listar_logs_recentes(self, limit: int = 20) -> list[dict]:
        """Mantido por compatibilidade (usado pelo dashboard da Fase 2.1)."""
        return self.listar_logs(limit=limit)

    def resumo_metricas(self) -> dict:
        from sqlalchemy import func

        total_execucoes, custo_total, latencia_media_ms, total_sucessos, total_fallbacks = (
            self.session.query(
                func.count(db.Execucao.id),
                func.coalesce(func.sum(db.Execucao.total_cost), 0),
                func.coalesce(func.avg(db.Execucao.total_latency_ms), 0),
                func.coalesce(func.sum(db.Execucao.success_count), 0),
                func.coalesce(func.sum(db.Execucao.fallback_count), 0),
            ).one()
        )

        total_decisoes = self.session.query(func.count(db.DecisaoRegistro.id)).scalar()
        total_decisoes_com_desvio = (
            self.session.query(func.count(db.DecisaoRegistro.id))
            .filter(db.DecisaoRegistro.status.in_([db.DecisionStatus.FALLBACK, db.DecisionStatus.DOWNGRADED]))
            .scalar()
        )

        top_model_row = (
            self.session.query(db.DecisaoRegistro.selected_model, func.count().label("n"))
            .group_by(db.DecisaoRegistro.selected_model)
            .order_by(func.count().desc())
            .first()
        )
        modelo_mais_usado = top_model_row[0] if top_model_row else None

        taxa_sucesso = (total_sucessos / total_decisoes) if total_decisoes else 0.0
        fallback_rate = (total_decisoes_com_desvio / total_decisoes) if total_decisoes else 0.0

        return {
            "total_execucoes": total_execucoes,
            "custo_total": float(custo_total),
            "latencia_media_ms": float(latencia_media_ms),
            "taxa_sucesso": taxa_sucesso,
            "fallback_rate": fallback_rate,
            "total_decisoes": total_decisoes,
            "total_decisoes_com_desvio": total_decisoes_com_desvio,
            "modelo_mais_usado": modelo_mais_usado,
        }

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
        projeto = db.Projeto(
            name=name, description=description, product_type=product_type,
            complexity=complexity, status=db.ProjectStatus(status),
        )
        self.session.add(projeto)
        self.session.flush()
        return str(projeto.id)

    def listar_projetos(self, limit: int = 50) -> list[dict]:
        projetos = self.session.query(db.Projeto).order_by(db.Projeto.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(p.id), "name": p.name, "description": p.description,
                "product_type": p.product_type, "complexity": p.complexity,
                "status": p.status.value, "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in projetos
        ]

    def obter_projeto(self, project_id: str) -> Optional[dict]:
        p = self.session.get(db.Projeto, project_id)
        if p is None:
            return None
        return {
            "id": str(p.id), "name": p.name, "description": p.description,
            "product_type": p.product_type, "complexity": p.complexity,
            "status": p.status.value, "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        }

    # ---- execuções (generalizado, com filtros) ----

    def listar_execucoes(
        self,
        limit: int = 50,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        from sqlalchemy import func

        query = self.session.query(db.Execucao)
        if project_id is not None:
            query = query.filter(db.Execucao.project_id == project_id)
        if status is not None:
            query = query.filter(db.Execucao.status == db.ExecutionStatus(status))
        execucoes = query.order_by(db.Execucao.created_at.desc()).limit(limit).all()

        resultados = []
        for e in execucoes:
            top = (
                self.session.query(db.DecisaoRegistro.selected_model, func.count().label("n"))
                .filter(db.DecisaoRegistro.execution_id == e.id)
                .group_by(db.DecisaoRegistro.selected_model)
                .order_by(func.count().desc())
                .first()
            )
            media_confianca = (
                self.session.query(func.avg(db.DecisaoRegistro.confidence_score))
                .filter(db.DecisaoRegistro.execution_id == e.id)
                .scalar()
            )
            resultados.append({
                "id": str(e.id), "project_id": str(e.project_id), "status": e.status.value,
                "total_cost": float(e.total_cost), "total_latency_ms": e.total_latency_ms,
                "success_count": e.success_count, "fallback_count": e.fallback_count,
                "created_at": e.created_at.isoformat(),
                "modelo_principal": top[0] if top else None,
                "confianca_media": float(media_confianca) if media_confianca is not None else None,
                "fallback_usado": e.fallback_count > 0,
            })
        return resultados

    def obter_execucao(self, execution_id: str) -> Optional[dict]:
        e = self.session.get(db.Execucao, execution_id)
        if e is None:
            return None
        return {
            "id": str(e.id), "project_id": str(e.project_id), "status": e.status.value,
            "total_cost": float(e.total_cost), "total_latency_ms": e.total_latency_ms,
            "success_count": e.success_count, "fallback_count": e.fallback_count,
            "created_at": e.created_at.isoformat(), "result_summary": e.result_summary,
        }

    # ---- logs (generalizado, com filtros e busca) ----

    def listar_logs(
        self,
        limit: int = 50,
        project_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        level: Optional[str] = None,
        busca: Optional[str] = None,
    ) -> list[dict]:
        query = self.session.query(db.Log)
        if project_id is not None:
            query = query.filter(db.Log.project_id == project_id)
        if execution_id is not None:
            query = query.filter(db.Log.execution_id == execution_id)
        if level is not None:
            query = query.filter(db.Log.level == db.LogLevel(level))
        if busca:
            like = f"%{busca}%"
            query = query.filter(db.Log.message.ilike(like) | db.Log.event_type.ilike(like))

        logs = query.order_by(db.Log.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(l.id),
                "project_id": str(l.project_id) if l.project_id else None,
                "execution_id": str(l.execution_id) if l.execution_id else None,
                "decision_record_id": str(l.decision_record_id) if l.decision_record_id else None,
                "level": l.level.value,
                "event_type": l.event_type,
                "message": l.message,
                "metadata": l.log_metadata,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ]
