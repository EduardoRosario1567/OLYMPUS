"""
Contrato que qualquer backend de persistência precisa cumprir.
O pipeline (olympus/pipeline.py) só conhece esta interface — nunca SQLAlchemy
nem sqlite3 diretamente. Isso é o que permite trocar Postgres por outro
backend sem tocar no motor de decisão nem no fluxo de negócio (princípio:
toda integração deve ser plugável).

Todos os métodos retornam/recebem IDs como string (não objetos ORM), para
não vazar detalhe de implementação de um backend específico pro pipeline.
"""

from typing import Protocol, Optional


class RepositorioPersistencia(Protocol):
    def criar_execucao(self, project_id: str) -> str:
        """Cria uma execução com status 'pending'/'running' e retorna seu id."""
        ...

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
        """Persiste um DecisaoRegistro e retorna seu id."""
        ...

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
        """Persiste um Log e retorna seu id."""
        ...

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
        ...

    def commit(self) -> None:
        ...

    # ---- leitura (necessária para dashboard/métricas — não existia na Fase 1) ----

    def listar_execucoes_recentes(self, limit: int = 20) -> list[dict]:
        """Retorna as execuções mais recentes, mais novas primeiro, como dicts simples
        (chaves: id, project_id, status, total_cost, total_latency_ms, success_count,
        fallback_count, created_at)."""
        ...

    def listar_logs_recentes(self, limit: int = 20) -> list[dict]:
        """Retorna os logs mais recentes, mais novos primeiro, como dicts simples
        (chaves: id, level, event_type, message, created_at)."""
        ...

    def resumo_metricas(self) -> dict:
        """Agrega métricas globais: total_execucoes, custo_total, latencia_media_ms,
        taxa_sucesso (0-1), fallback_rate (0-1), total_decisoes,
        total_decisoes_com_desvio, modelo_mais_usado (str | None)."""
        ...

    # ---- projetos (Fase 2.2 — projeto agora é entidade real) ----

    def criar_projeto(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        product_type: Optional[str] = None,
        complexity: Optional[str] = None,
        status: str = "active",
    ) -> str:
        """Cria um projeto e retorna seu id. Fluxo de criação completo pela
        interface ainda não existe (fica como 'em breve') — isso é usado por
        scripts/seed e pela futura tela de criação."""
        ...

    def listar_projetos(self, limit: int = 50) -> list[dict]:
        """Retorna projetos, mais recentes primeiro (chaves: id, name, description,
        product_type, complexity, status, created_at, updated_at)."""
        ...

    def obter_projeto(self, project_id: str) -> Optional[dict]:
        ...

    # ---- execuções (leitura generalizada, com filtros) ----

    def listar_execucoes(
        self,
        limit: int = 50,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Lista execuções mais recentes primeiro, com filtros opcionais."""
        ...

    def obter_execucao(self, execution_id: str) -> Optional[dict]:
        ...

    # ---- logs (leitura generalizada, com filtros e busca textual) ----

    def listar_logs(
        self,
        limit: int = 50,
        project_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        level: Optional[str] = None,
        busca: Optional[str] = None,
    ) -> list[dict]:
        """Lista logs mais recentes primeiro, com filtros opcionais e busca
        textual simples (LIKE) em message/event_type."""
        ...

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
        ...

    def obter_execution_result(self, result_id: str) -> Optional[dict]:
        """Obtém um resultado de execução por id."""
        ...

    def obter_execution_result_por_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém o resultado de execução associado a um decision_record_id."""
        ...

    def obter_decisao(self, decision_record_id: str) -> Optional[dict]:
        """Obtém um registro de decisão por id."""
        ...

    def listar_execution_results(
        self,
        limit: int = 50,
        execution_id: Optional[str] = None,
        decision_record_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista resultados de execução com filtros opcionais."""
        ...

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
        ...

    def obter_quality_evaluation(self, evaluation_id: str) -> Optional[dict]:
        """Obtém uma avaliação de qualidade por id."""
        ...

    def listar_quality_evaluations(
        self,
        limit: int = 50,
        execution_result_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista avaliações de qualidade com filtros opcionais."""
        ...
