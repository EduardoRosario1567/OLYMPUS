-- Olympus — Schema mínimo persistente (Fase 1 -> 2)
-- Postgres. Versão enxuta: apenas decisao_registros, execucoes, logs.
-- project_id / task_id ficam opcionais até o restante da modelagem existir.

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- para gen_random_uuid()

-- ==== ENUMS =================================================================

CREATE TYPE execution_status AS ENUM (
    'pending', 'running', 'completed', 'failed', 'partial'
);

CREATE TYPE decision_status AS ENUM (
    'approved', 'downgraded', 'fallback', 'rejected', 'retried'
);

CREATE TYPE log_level AS ENUM (
    'debug', 'info', 'warning', 'error', 'critical'
);

CREATE TYPE project_status AS ENUM (
    'active', 'paused', 'archived'
);

-- ==== TABELA: projetos =======================================================
-- Fase 2.2: projeto deixa de ser um project_id solto e vira entidade real.

CREATE TABLE projetos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    description     TEXT NULL,
    product_type    VARCHAR(80) NULL,
    complexity      VARCHAR(40) NULL,
    status          project_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ==== TABELA: execucoes =====================================================
-- Criada antes de decisao_registros por causa da FK em decisao_registros.execution_id

CREATE TABLE execucoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL,
    decision_record_id  UUID NULL, -- FK adicionada depois (referência circular com decisao_registros)
    status              execution_status NOT NULL DEFAULT 'pending',
    started_at          TIMESTAMP NULL,
    finished_at         TIMESTAMP NULL,
    total_cost          NUMERIC(12,6) NOT NULL DEFAULT 0,
    total_latency_ms    INTEGER NOT NULL DEFAULT 0,
    success_count       INTEGER NOT NULL DEFAULT 0,
    fallback_count      INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT NULL,
    result_summary      TEXT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ==== TABELA: decisao_registros ============================================

CREATE TABLE decisao_registros (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NULL,  -- FK adicionada depois de projetos existir (ver ALTER TABLE abaixo)
    task_id                 UUID NULL,
    execution_id            UUID NULL REFERENCES execucoes(id),
    input_type              VARCHAR(50) NOT NULL,
    task_description        TEXT NOT NULL,
    selected_provider       VARCHAR(80) NOT NULL,
    selected_model          VARCHAR(120) NOT NULL,
    candidate_models        JSONB NOT NULL DEFAULT '[]',
    policy_applied          VARCHAR(120) NOT NULL,
    decision_reason         TEXT NOT NULL,
    confidence_score        NUMERIC(5,2) NOT NULL DEFAULT 0,
    estimated_cost          NUMERIC(12,6) NOT NULL DEFAULT 0,
    estimated_latency_ms    INTEGER NOT NULL DEFAULT 0,
    status                  decision_status NOT NULL DEFAULT 'approved',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

-- fecha a referência circular: execucoes.decision_record_id -> decisao_registros.id
ALTER TABLE execucoes
    ADD CONSTRAINT fk_execucoes_decision_record
    FOREIGN KEY (decision_record_id) REFERENCES decisao_registros(id);

-- Fase 2.2: projeto agora é entidade real — liga as 3 tabelas a projetos(id).
-- execucoes.project_id já era NOT NULL; decisao_registros/logs continuam NULL-able.
ALTER TABLE execucoes
    ADD CONSTRAINT fk_execucoes_projeto
    FOREIGN KEY (project_id) REFERENCES projetos(id);

ALTER TABLE decisao_registros
    ADD CONSTRAINT fk_decisao_registros_projeto
    FOREIGN KEY (project_id) REFERENCES projetos(id);

-- ==== TABELA: execution_results =============================================
-- PATCH 004B: resultado real de execução, separado da decisão
-- PATCH 004C: execution_result_status ENUM

CREATE TYPE execution_result_status AS ENUM (
    'success',
    'timeout',
    'provider_error',
    'billing_error',
    'unavailable',
    'rate_limited',
    'authentication_error',
    'malformed_response',
    'unknown_error'
);

CREATE TABLE execution_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id            UUID NOT NULL REFERENCES execucoes(id),
    decision_record_id      UUID NOT NULL REFERENCES decisao_registros(id),
    requested_model         VARCHAR(120) NOT NULL,
    actual_model            VARCHAR(120) NOT NULL,
    provider                VARCHAR(80) NOT NULL,
    output                  TEXT NOT NULL,
    latency_ms              INTEGER NOT NULL DEFAULT 0,
    cost                    NUMERIC(12,6) NOT NULL DEFAULT 0,
    success                 BOOLEAN NOT NULL DEFAULT TRUE,
    error                   TEXT NULL,
    status                  execution_result_status NOT NULL DEFAULT 'success',
    correlation_id          VARCHAR(80) NULL,
    usage                   JSONB NULL DEFAULT '{}',
    metadata                JSONB NULL DEFAULT '{}',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_execution_results_execution_id    ON execution_results(execution_id);
CREATE INDEX idx_execution_results_decision_record_id ON execution_results(decision_record_id);
CREATE INDEX idx_execution_results_created_at      ON execution_results(created_at);


-- ==== TABELA: quality_evaluations ===========================================
-- PATCH 005D: avaliação de qualidade, separada da decisão e do resultado de execução

CREATE TABLE quality_evaluations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_result_id     UUID NOT NULL REFERENCES execution_results(id),
    quality_score           NUMERIC(5,2) NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    passed                  BOOLEAN NOT NULL DEFAULT FALSE,
    evaluator               VARCHAR(80) NOT NULL,
    reason                  TEXT NOT NULL,
    criteria                JSONB NOT NULL DEFAULT '{}',
    metadata                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_quality_evaluations_execution_result_id ON quality_evaluations(execution_result_id);
CREATE INDEX idx_quality_evaluations_created_at ON quality_evaluations(created_at);


-- ==== TABELA: logs ===========================================================

CREATE TABLE logs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NULL REFERENCES projetos(id),
    execution_id            UUID NULL REFERENCES execucoes(id),
    decision_record_id      UUID NULL REFERENCES decisao_registros(id),
    level                   log_level NOT NULL DEFAULT 'info',
    event_type              VARCHAR(80) NOT NULL,
    message                 TEXT NOT NULL,
    metadata                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ==== ÍNDICES =================================================================

CREATE INDEX idx_decisao_registros_project_id    ON decisao_registros(project_id);
CREATE INDEX idx_decisao_registros_execution_id  ON decisao_registros(execution_id);
CREATE INDEX idx_decisao_registros_created_at    ON decisao_registros(created_at);

CREATE INDEX idx_execucoes_project_id            ON execucoes(project_id);
CREATE INDEX idx_execucoes_status                ON execucoes(status);
CREATE INDEX idx_execucoes_created_at            ON execucoes(created_at);

CREATE INDEX idx_logs_project_id                 ON logs(project_id);
CREATE INDEX idx_logs_execution_id               ON logs(execution_id);
CREATE INDEX idx_logs_decision_record_id         ON logs(decision_record_id);
CREATE INDEX idx_logs_level                      ON logs(level);
CREATE INDEX idx_logs_created_at                 ON logs(created_at);

CREATE INDEX idx_projetos_status                 ON projetos(status);
CREATE INDEX idx_projetos_created_at             ON projetos(created_at);

-- ==== TRIGGERS: updated_at automático =========================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_decisao_registros_updated_at
    BEFORE UPDATE ON decisao_registros
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_execucoes_updated_at
    BEFORE UPDATE ON execucoes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_projetos_updated_at
    BEFORE UPDATE ON projetos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
