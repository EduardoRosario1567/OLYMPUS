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
        result = db.ExecutionResult(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            requested_model=requested_model,
            actual_model=actual_model,
            provider=provider,
            output=output,
            latency_ms=latency_ms,
            cost=0.0 if cost is None else cost,
            success=1 if success else 0,
            error=error,
            status=status,
            correlation_id=correlation_id,
            usage=usage or {},
            metadata_=metadata or {},
        )
        self.session.add(result)
        self.session.flush()
        return str(result.id)

    def obter_execution_result(self, result_id: str) -> Optional[dict]:
        """Obtém um resultado de execução por id."""
        result = self.session.get(db.ExecutionResult, result_id)
        if result is None:
            return None
        return {
            "id": str(result.id),
            "execution_id": str(result.execution_id),
            "decision_record_id": str(result.decision_record_id),
            "requested_model": result.requested_model,
            "actual_model": result.actual_model,
            "provider": result.provider,
            "output": result.output,
            "latency_ms": result.latency_ms,
            "cost": float(result.cost),
            "success": bool(result.success),
            "error": result.error,
            "status": result.status,
            "correlation_id": result.correlation_id,
            "usage": result.usage,
            "metadata": result.metadata_,
            "created_at": result.created_at.isoformat(),
        }

    def obter_execution_result_por_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém o resultado de execução associado a um decision_record_id."""
        result = (
            self.session.query(db.ExecutionResult)
            .filter(db.ExecutionResult.decision_record_id == decision_record_id)
            .first()
        )
        if result is None:
            return None
        return {
            "id": str(result.id),
            "execution_id": str(result.execution_id),
            "decision_record_id": str(result.decision_record_id),
            "requested_model": result.requested_model,
            "actual_model": result.actual_model,
            "provider": result.provider,
            "output": result.output,
            "latency_ms": result.latency_ms,
            "cost": float(result.cost),
            "success": bool(result.success),
            "error": result.error,
            "status": result.status,
            "correlation_id": result.correlation_id,
            "usage": result.usage,
            "metadata": result.metadata_,
            "created_at": result.created_at.isoformat(),
        }

    def obter_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém um registro de decisão por id."""
        from olympus.db import models as db
        registro = self.session.get(db.DecisaoRegistro, decision_record_id)
        if registro is None:
            return None
        return {
            "id": str(registro.id),
            "project_id": str(registro.project_id) if registro.project_id else None,
            "task_id": registro.task_id,
            "execution_id": str(registro.execution_id) if registro.execution_id else None,
            "input_type": registro.input_type,
            "task_description": registro.task_description,
            "selected_provider": registro.selected_provider,
            "selected_model": registro.selected_model,
            "candidate_models": registro.candidate_models,
            "policy_applied": registro.policy_applied,
            "decision_reason": registro.decision_reason,
            "confidence_score": float(registro.confidence_score),
            "estimated_cost": float(registro.estimated_cost),
            "estimated_latency_ms": registro.estimated_latency_ms,
            "status": registro.status.value if registro.status else None,
            "created_at": registro.created_at.isoformat() if registro.created_at else None,
            "updated_at": registro.updated_at.isoformat() if registro.updated_at else None,
        }

    def listar_execution_results(
        self,
        limit: int = 50,
        execution_id: Optional[str] = None,
        decision_record_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista resultados de execução com filtros opcionais."""
        query = self.session.query(db.ExecutionResult)
        if execution_id is not None:
            query = query.filter(db.ExecutionResult.execution_id == execution_id)
        if decision_record_id is not None:
            query = query.filter(db.ExecutionResult.decision_record_id == decision_record_id)
        results = query.order_by(db.ExecutionResult.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(r.id),
                "execution_id": str(r.execution_id),
                "decision_record_id": str(r.decision_record_id),
                "requested_model": r.requested_model,
                "actual_model": r.actual_model,
                "provider": r.provider,
                "output": r.output,
                "latency_ms": r.latency_ms,
                "cost": float(r.cost),
                "success": bool(r.success),
                "error": r.error,
                "status": r.status,
                "correlation_id": r.correlation_id,
                "usage": r.usage,
                "metadata": r.metadata_,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]

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
        from olympus.db import models as db
        eval_obj = db.QualityEvaluation(
            execution_result_id=execution_result_id,
            quality_score=quality_score,
            passed=1 if passed else 0,
            evaluator=evaluator,
            reason=reason,
            criteria=criteria or {},
            metadata_=metadata or {},
        )
        self.session.add(eval_obj)
        self.session.flush()
        return str(eval_obj.id)

    def obter_quality_evaluation(self, evaluation_id: str) -> Optional[dict]:
        """Obtém uma avaliação de qualidade por id."""
        from olympus.db import models as db
        result = self.session.get(db.QualityEvaluation, evaluation_id)
        if result is None:
            return None
        return {
            "id": str(result.id),
            "execution_result_id": str(result.execution_result_id),
            "quality_score": float(result.quality_score),
            "passed": bool(result.passed),
            "evaluator": result.evaluator,
            "reason": result.reason,
            "criteria": result.criteria,
            "metadata": result.metadata_,
            "created_at": result.created_at.isoformat(),
        }

    def listar_quality_evaluations(
        self,
        limit: int = 50,
        execution_result_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista avaliações de qualidade com filtros opcionais."""
        from olympus.db import models as db
        query = self.session.query(db.QualityEvaluation)
        if execution_result_id is not None:
            query = query.filter(db.QualityEvaluation.execution_result_id == execution_result_id)
        results = query.order_by(db.QualityEvaluation.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(r.id),
                "execution_result_id": str(r.execution_result_id),
                "quality_score": float(r.quality_score),
                "passed": bool(r.passed),
                "evaluator": r.evaluator,
                "reason": r.reason,
                "criteria": r.criteria,
                "metadata": r.metadata_,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
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
        result = db.ExecutionResult(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            requested_model=requested_model,
            actual_model=actual_model,
            provider=provider,
            output=output,
            latency_ms=latency_ms,
            cost=0.0 if cost is None else cost,
            success=1 if success else 0,
            error=error,
            status=status,
            correlation_id=correlation_id,
            usage=usage or {},
            metadata_=metadata or {},
        )
        self.session.add(result)
        self.session.flush()
        return str(result.id)

    def obter_execution_result(self, result_id: str) -> Optional[dict]:
        """Obtém um resultado de execução por id."""
        result = self.session.get(db.ExecutionResult, result_id)
        if result is None:
            return None
        return {
            "id": str(result.id),
            "execution_id": str(result.execution_id),
            "decision_record_id": str(result.decision_record_id),
            "requested_model": result.requested_model,
            "actual_model": result.actual_model,
            "provider": result.provider,
            "output": result.output,
            "latency_ms": result.latency_ms,
            "cost": float(result.cost),
            "success": bool(result.success),
            "error": result.error,
            "status": result.status,
            "correlation_id": result.correlation_id,
            "usage": result.usage,
            "metadata": result.metadata_,
            "created_at": result.created_at.isoformat(),
        }

    def obter_execution_result_por_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém o resultado de execução associado a um decision_record_id."""
        result = (
            self.session.query(db.ExecutionResult)
            .filter(db.ExecutionResult.decision_record_id == decision_record_id)
            .first()
        )
        if result is None:
            return None
        return {
            "id": str(result.id),
            "execution_id": str(result.execution_id),
            "decision_record_id": str(result.decision_record_id),
            "requested_model": result.requested_model,
            "actual_model": result.actual_model,
            "provider": result.provider,
            "output": result.output,
            "latency_ms": result.latency_ms,
            "cost": float(result.cost),
            "success": bool(result.success),
            "error": result.error,
            "status": result.status,
            "correlation_id": result.correlation_id,
            "usage": result.usage,
            "metadata": result.metadata_,
            "created_at": result.created_at.isoformat(),
        }

    def obter_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém um registro de decisão por id."""
        from olympus.db import models as db
        registro = self.session.get(db.DecisaoRegistro, decision_record_id)
        if registro is None:
            return None
        return {
            "id": str(registro.id),
            "project_id": str(registro.project_id) if registro.project_id else None,
            "task_id": registro.task_id,
            "execution_id": str(registro.execution_id) if registro.execution_id else None,
            "input_type": registro.input_type,
            "task_description": registro.task_description,
            "selected_provider": registro.selected_provider,
            "selected_model": registro.selected_model,
            "candidate_models": registro.candidate_models,
            "policy_applied": registro.policy_applied,
            "decision_reason": registro.decision_reason,
            "confidence_score": float(registro.confidence_score),
            "estimated_cost": float(registro.estimated_cost),
            "estimated_latency_ms": registro.estimated_latency_ms,
            "status": registro.status.value if registro.status else None,
            "created_at": registro.created_at.isoformat() if registro.created_at else None,
            "updated_at": registro.updated_at.isoformat() if registro.updated_at else None,
        }

    def listar_execution_results(
        self,
        limit: int = 50,
        execution_id: Optional[str] = None,
        decision_record_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista resultados de execução com filtros opcionais."""
        query = self.session.query(db.ExecutionResult)
        if execution_id is not None:
            query = query.filter(db.ExecutionResult.execution_id == execution_id)
        if decision_record_id is not None:
            query = query.filter(db.ExecutionResult.decision_record_id == decision_record_id)
        results = query.order_by(db.ExecutionResult.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(r.id),
                "execution_id": str(r.execution_id),
                "decision_record_id": str(r.decision_record_id),
                "requested_model": r.requested_model,
                "actual_model": r.actual_model,
                "provider": r.provider,
                "output": r.output,
                "latency_ms": r.latency_ms,
                "cost": float(r.cost),
                "success": bool(r.success),
                "error": r.error,
                "status": r.status,
                "correlation_id": r.correlation_id,
                "usage": r.usage,
                "metadata": r.metadata_,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]

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
        from olympus.db import models as db
        eval_obj = db.QualityEvaluation(
            execution_result_id=execution_result_id,
            quality_score=quality_score,
            passed=1 if passed else 0,
            evaluator=evaluator,
            reason=reason,
            criteria=criteria or {},
            metadata_=metadata or {},
        )
        self.session.add(eval_obj)
        self.session.flush()
        return str(eval_obj.id)

    def obter_quality_evaluation(self, evaluation_id: str) -> Optional[dict]:
        """Obtém uma avaliação de qualidade por id."""
        from olympus.db import models as db
        result = self.session.get(db.QualityEvaluation, evaluation_id)
        if result is None:
            return None
        return {
            "id": str(result.id),
            "execution_result_id": str(result.execution_result_id),
            "quality_score": float(result.quality_score),
            "passed": bool(result.passed),
            "evaluator": result.evaluator,
            "reason": result.reason,
            "criteria": result.criteria,
            "metadata": result.metadata_,
            "created_at": result.created_at.isoformat(),
        }

    def listar_quality_evaluations(
        self,
        limit: int = 50,
        execution_result_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista avaliações de qualidade com filtros opcionais."""
        from olympus.db import models as db
        query = self.session.query(db.QualityEvaluation)
        if execution_result_id is not None:
            query = query.filter(db.QualityEvaluation.execution_result_id == execution_result_id)
        results = query.order_by(db.QualityEvaluation.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(r.id),
                "execution_result_id": str(r.execution_result_id),
                "quality_score": float(r.quality_score),
                "passed": bool(r.passed),
                "evaluator": r.evaluator,
                "reason": r.reason,
                "criteria": r.criteria,
                "metadata": r.metadata_,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]
