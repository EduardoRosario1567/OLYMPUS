"""
Pipeline de execução do Olympus — liga as peças do cérebro (classifier,
registry, decision_engine) à persistência, através do protocolo
RepositorioPersistencia. Não importa se o repositório é Postgres real ou
o gêmeo SQLite de dev: o pipeline não muda.

Integração de roteamento (PATCH 003A):
- router: Optional[RoutingAdapter] injetado via dependency injection
- DECISION (processar_tarefa) permanece pura — sem execução real
- EXECUTION (executar_decisao) separada e opcional, usa router quando injetado
"""

from typing import Optional
from olympus.models import Tarefa
from olympus.classifier import TaskClassifier
from olympus.registry import ModelRegistry
from olympus.decision_engine import DecisionEngine
from olympus.db.interfaces import RepositorioPersistencia
from olympus.routing.interfaces import RoutingAdapter, RoutingExecutionResult


class OlympusPipeline:
    def __init__(
        self,
        classifier: TaskClassifier,
        registry: ModelRegistry,
        engine: DecisionEngine,
        repo: RepositorioPersistencia,
        router: Optional[RoutingAdapter] = None,
    ) -> None:
        self.classifier = classifier
        self.registry = registry
        self.engine = engine
        self.repo = repo
        self.router = router

    def iniciar_execucao(self, project_id: str) -> str:
        if self.repo.obter_projeto(project_id) is None:
            raise ValueError(
                f"Projeto '{project_id}' não existe. Crie o projeto (repo.criar_projeto) antes de iniciar uma execução."
            )
        return self.repo.criar_execucao(project_id)

    def processar_tarefa(self, tarefa: Tarefa, project_id: str, execution_id: str) -> tuple:
        """Classifica, decide e persiste (decisão + log) uma tarefa. Retorna (decisao, decision_record_id)."""
        if tarefa.tipo is None:
            tarefa.tipo = self.classifier.classify(tarefa.descricao)

        decisao = self.engine.decidir(tarefa)
        modelo = self.registry.obter(decisao.modelo_escolhido) if decisao.modelo_escolhido else None

        policy_applied = self._nome_politica(tarefa)

        decision_record_id = self.repo.registrar_decisao(
            tarefa_id=tarefa.id,
            modelo_escolhido=decisao.modelo_escolhido,
            candidatos_avaliados=decisao.candidatos_avaliados,
            motivo=decisao.motivo,
            confianca=decisao.confianca,
            decisao_status=decisao.decisao_status,
            input_type=tarefa.tipo.value,
            task_description=tarefa.descricao,
            selected_provider=modelo.provedor if modelo else "desconhecido",
            policy_applied=policy_applied,
            estimated_cost=decisao.custo_estimado,
            estimated_latency_ms=decisao.latencia_estimada_ms,
            project_id=project_id,
            execution_id=execution_id,
        )

        nivel_log = "warning" if (decisao.fallback_usado or decisao.downgrade_usado) else "info"
        self.repo.registrar_log(
            event_type="decisao_tomada",
            message=f"Tarefa {tarefa.id}: modelo '{decisao.modelo_escolhido}' — {decisao.decisao_status}",
            level=nivel_log,
            project_id=project_id,
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            metadata={
                "fallback_usado": decisao.fallback_usado,
                "downgrade_usado": decisao.downgrade_usado,
                "tipo_tarefa": tarefa.tipo.value,
            },
        )

        return decisao, decision_record_id

    def executar_decisao(
        self,
        decisao: "DecisaoRegistro",
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[RoutingExecutionResult]:
        """
        Executa a decisão via RoutingAdapter injetado.

        Separado de processar_tarefa para manter DECISION e EXECUTION distintas:
        - processar_tarefa: classifica, decide, persiste decisão (sem execução real)
        - executar_decisao: executa o modelo escolhido via router (opcional)

        Args:
            decisao: DecisaoRegistro retornada por processar_tarefa
            prompt: Texto do prompt para executar
            max_tokens: Limite opcional de tokens de saída
            temperature: Temperatura opcional de sampling

        Returns:
            RoutingExecutionResult se router injetado e decisão tem modelo,
            None se router não injetado ou decisão sem modelo.

        Não altera comportamento existente quando router=None.
        """
        if self.router is None:
            return None

        if not decisao.modelo_escolhido:
            return None

        return self.router.execute(
            decisao.modelo_escolhido,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def finalizar_execucao(self, execution_id: str, decisoes: list) -> None:
        total_custo = sum(d.custo_estimado for d in decisoes)
        total_latencia = sum(d.latencia_estimada_ms for d in decisoes)
        total_fallback = sum(1 for d in decisoes if d.fallback_usado or d.downgrade_usado)
        status = "completed" if all(d.modelo_escolhido for d in decisoes) else "partial"

        self.repo.finalizar_execucao(
            execution_id,
            status=status,
            total_cost=total_custo,
            total_latency_ms=total_latencia,
            success_count=sum(1 for d in decisoes if d.modelo_escolhido),
            fallback_count=total_fallback,
            result_summary=f"{len(decisoes)} tarefa(s) processada(s), {total_fallback} com fallback/downgrade.",
        )
        self.repo.commit()

    def registrar_resultado_execucao(
        self,
        *,
        execution_id: str,
        decision_record_id: str,
        execution_result: "RoutingExecutionResult",
    ) -> str:
        """
        Persiste o resultado real da execução separadamente da decisão.

        DECISION (decisao_registros) = "O que Olympus decidiu?"
        EXECUTION RESULT (execution_results) = "O que realmente aconteceu?"

        Args:
            execution_id: ID da execução (FK)
            decision_record_id: ID do registro de decisão (FK)
            execution_result: RoutingExecutionResult retornado pelo adapter

        Returns:
            ID do execution_result persistido
        """
        # Usar status do RoutingExecutionResult (ExecutionStatus enum value)
        status = execution_result.status if execution_result.status else ("success" if execution_result.success else "failed")
        return self.repo.registrar_execution_result(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            requested_model=execution_result.requested_model,
            actual_model=execution_result.actual_model,
            provider=execution_result.provider,
            output=execution_result.output,
            latency_ms=execution_result.latency_ms,
            cost=execution_result.cost,
            success=execution_result.success,
            error=execution_result.error,
            status=status,
            correlation_id=execution_result.metadata.get("correlation_id") if execution_result.metadata else None,
            usage=execution_result.metadata.get("usage") if execution_result.metadata else None,
            metadata=execution_result.metadata,
        )

    def registrar_avaliacao_qualidade(
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
        """
        Persiste explicitamente uma avaliação de qualidade.

        Pipeline NÃO escolhe/invoca Judge — caller é responsável por:
        1. JudgeAdapter.evaluate(context) → JudgeResult
        2. Pipeline.registrar_avaliacao_qualidade(...)

        Args:
            execution_result_id: FK para execution_results
            quality_score: 0.0 a 1.0 (exatamente do JudgeResult)
            passed: quality_score >= threshold
            evaluator: string identificadora do evaluator (ex: "rule_based")
            reason: explicação legível
            criteria: scores por critério
            metadata: extensível (weights, threshold, etc.)

        Returns:
            ID da quality_evaluation persistida
        """
        return self.repo.registrar_quality_evaluation(
            execution_result_id=execution_result_id,
            quality_score=quality_score,
            passed=passed,
            evaluator=evaluator,
            reason=reason,
            criteria=criteria,
            metadata=metadata,
        )

    @staticmethod
    def _nome_politica(tarefa: Tarefa) -> str:
        if tarefa.urgente:
            return "urgencia_menor_latencia"
        if tarefa.critica:
            return "critica_maior_confiabilidade"
        return "padrao_menor_custo"
