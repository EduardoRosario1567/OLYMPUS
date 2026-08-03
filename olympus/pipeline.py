"""
Pipeline de execução do Olympus — liga as peças do cérebro (classifier,
registry, decision_engine) à persistência, através do protocolo
RepositorioPersistencia. Não importa se o repositório é Postgres real ou
o gêmeo SQLite de dev: o pipeline não muda.
"""

from olympus.models import Tarefa
from olympus.classifier import TaskClassifier
from olympus.registry import ModelRegistry
from olympus.decision_engine import DecisionEngine
from olympus.db.interfaces import RepositorioPersistencia


class OlympusPipeline:
    def __init__(
        self,
        classifier: TaskClassifier,
        registry: ModelRegistry,
        engine: DecisionEngine,
        repo: RepositorioPersistencia,
    ) -> None:
        self.classifier = classifier
        self.registry = registry
        self.engine = engine
        self.repo = repo

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

    @staticmethod
    def _nome_politica(tarefa: Tarefa) -> str:
        if tarefa.urgente:
            return "urgencia_menor_latencia"
        if tarefa.critica:
            return "critica_maior_confiabilidade"
        return "padrao_menor_custo"
