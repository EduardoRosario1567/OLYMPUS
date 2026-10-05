"""
Camada ORM (SQLAlchemy) — espelha schema.sql.
Alvo: Postgres (usa UUID e JSONB nativos do dialeto).
"""

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Numeric, DateTime, ForeignKey, Enum as SAEnum, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ExecutionResultStatus(str, enum.Enum):
    """Status técnico do resultado de execução (PATCH 004C).

    Distingue falha técnica de execução de qualidade da resposta.
    "success" significa apenas: execução técnica recebeu e parseou resposta válida.
    NÃO significa resposta de boa qualidade.
    """
    SUCCESS = "success"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    BILLING_ERROR = "billing_error"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_ERROR = "authentication_error"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN_ERROR = "unknown_error"


class DecisionStatus(str, enum.Enum):
    APPROVED = "approved"
    DOWNGRADED = "downgraded"
    FALLBACK = "fallback"
    REJECTED = "rejected"
    RETRIED = "retried"


class LogLevel(str, enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Projeto(Base):
    __tablename__ = "projetos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    product_type = Column(String(80), nullable=True)
    complexity = Column(String(40), nullable=True)
    status = Column(SAEnum(ProjectStatus, name="project_status"), nullable=False, default=ProjectStatus.ACTIVE)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Execucao(Base):
    __tablename__ = "execucoes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projetos.id"), nullable=False)
    decision_record_id = Column(UUID(as_uuid=True), ForeignKey("decisao_registros.id"), nullable=True)
    status = Column(SAEnum(ExecutionStatus, name="execution_status"), nullable=False, default=ExecutionStatus.PENDING)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    total_cost = Column(Numeric(12, 6), nullable=False, default=0)
    total_latency_ms = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    fallback_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    decisoes = relationship("DecisaoRegistro", back_populates="execucao", foreign_keys="DecisaoRegistro.execution_id")
    logs = relationship("Log", back_populates="execucao")


class DecisaoRegistro(Base):
    __tablename__ = "decisao_registros"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projetos.id"), nullable=True)
    task_id = Column(UUID(as_uuid=True), nullable=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("execucoes.id"), nullable=True)
    input_type = Column(String(50), nullable=False)
    task_description = Column(Text, nullable=False)
    selected_provider = Column(String(80), nullable=False)
    selected_model = Column(String(120), nullable=False)
    candidate_models = Column(JSONB, nullable=False, default=list)
    policy_applied = Column(String(120), nullable=False)
    decision_reason = Column(Text, nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=False, default=0)
    estimated_cost = Column(Numeric(12, 6), nullable=False, default=0)
    estimated_latency_ms = Column(Integer, nullable=False, default=0)
    status = Column(SAEnum(DecisionStatus, name="decision_status"), nullable=False, default=DecisionStatus.APPROVED)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    execucao = relationship("Execucao", back_populates="decisoes", foreign_keys=[execution_id])
    logs = relationship("Log", back_populates="decisao")


class Log(Base):
    __tablename__ = "logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projetos.id"), nullable=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("execucoes.id"), nullable=True)
    decision_record_id = Column(UUID(as_uuid=True), ForeignKey("decisao_registros.id"), nullable=True)
    level = Column(SAEnum(LogLevel, name="log_level"), nullable=False, default=LogLevel.INFO)
    event_type = Column(String(80), nullable=False)
    message = Column(Text, nullable=False)
    log_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    execucao = relationship("Execucao", back_populates="logs")
    decisao = relationship("DecisaoRegistro", back_populates="logs")


class ExecutionResult(Base):
    __tablename__ = "execution_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("execucoes.id"), nullable=False)
    decision_record_id = Column(UUID(as_uuid=True), ForeignKey("decisao_registros.id"), nullable=False)
    requested_model = Column(String(120), nullable=False)
    actual_model = Column(String(120), nullable=False)
    provider = Column(String(80), nullable=False)
    output = Column(Text, nullable=False)
    latency_ms = Column(Integer, nullable=False, default=0)
    cost = Column(Numeric(12, 6), nullable=False, default=0)
    success = Column(Integer, nullable=False, default=0)  # 0/1 for boolean
    error = Column(Text, nullable=True)
    status = Column(SAEnum(ExecutionResultStatus, name="execution_result_status"), nullable=False, default=ExecutionResultStatus.SUCCESS)
    correlation_id = Column(String(80), nullable=True)
    usage = Column(JSONB, nullable=True, default=dict)
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class QualityEvaluation(Base):
    """Avaliação de qualidade de um resultado de execução — PATCH 005D.

    Entidade separada de DecisionRecord e ExecutionResult.
    Persiste exatamente o quality_score do JudgeResult.
    """
    __tablename__ = "quality_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_result_id = Column(UUID(as_uuid=True), ForeignKey("execution_results.id"), nullable=False)
    quality_score = Column(Numeric(5, 2), nullable=False)  # 0.00 a 1.00
    passed = Column(Integer, nullable=False, default=0)  # 0/1 for boolean
    evaluator = Column(String(80), nullable=False)
    reason = Column(Text, nullable=False)
    criteria = Column(JSONB, nullable=False, default=dict)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Constraint: quality_score between 0 and 1
    __table_args__ = (
        CheckConstraint('quality_score >= 0 AND quality_score <= 1', name='ck_quality_score_range'),
    )
