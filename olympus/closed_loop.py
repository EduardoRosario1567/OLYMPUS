"""
Closed Loop Entry Point — PATCH 003B

Composes existing Olympus components + OmniRouteAdapter for real execution.

Fluxo:
1. TaskClassifier classifica a tarefa
2. ModelRegistry fornece candidatos
3. DecisionEngine decide (policy, fallback, downgrade, custo)
4. Pipeline persiste decisão + log
5. RoutingAdapter (OmniRouteAdapter) executa o modelo real
6. Retorna RoutingExecutionResult com output real

Olympus Core NÃO importa OmniRoute — apenas usa RoutingAdapter protocol.
OmniRouteAdapter é injetado no Pipeline via dependency injection.
"""

import os
from dataclasses import dataclass
from typing import Optional

from olympus.classifier import TaskClassifier
from olympus.registry import ModelRegistry
from olympus.decision_engine import DecisionEngine
from olympus.pipeline import OlympusPipeline
from olympus.db.interfaces import RepositorioPersistencia
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.routing.interfaces import RoutingAdapter, RoutingExecutionResult
from olympus.models import Tarefa, TaskType, Modelo


@dataclass
class ClosedLoopResult:
    """Resultado estruturado do fluxo completo fechado."""
    task: str
    task_type: str
    policy: str
    selected_model: str
    decision_confidence: float
    decision_reason: str
    actual_model: str
    provider: str
    success: bool
    latency_ms: int
    cost: float
    output: str
    correlation_id: Optional[str] = None
    metadata: Optional[dict] = None


def build_default_registry() -> ModelRegistry:
    """Constrói registry com modelos concretos para Closed Loop 001.

    Apenas modelos concretos e comprovados — NENHUM alias automático.
    O DecisionEngine escolhe explicitamente via policy existente.
    """
    registry = ModelRegistry()

    # 1. Modelo principal: Cohere North Mini Code (gratuito, bom para coding/tool use)
    registry.registrar(Modelo(
        id="openrouter/cohere/north-mini-code:free",
        nome="Cohere North Mini Code (free)",
        provedor="openrouter",
        capacidades=[TaskType.ARQUITETURA, TaskType.CODIGO, TaskType.TESTES],
        custo_estimado=0.0,
        latencia_estimada=0.5,      # estimativa
        confiabilidade=0.85,        # estimativa
    ))

    # 2. Fallback: NVIDIA Nemotron 3.5 Lightning (gratuito, bom para coding)
    registry.registrar(Modelo(
        id="openrouter/nvidia/nemotron-3.5-lightning:free",
        nome="NVIDIA Nemotron 3.5 Lightning (free)",
        provedor="openrouter",
        capacidades=[TaskType.CODIGO, TaskType.TESTES, TaskType.ARQUITETURA],
        custo_estimado=0.0,
        latencia_estimada=0.6,      # estimativa
        confiabilidade=0.80,        # estimativa
    ))

    return registry


def build_omniroute_adapter(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_seconds: float = 30.0,
):
    """Constrói OmniRouteAdapter com configuração padrão.

    Args:
        base_url: URL do OmniRoute (default: http://127.0.0.1:20128 ou OMNIROUTE_BASE_URL env)
        api_key: API key opcional (default: OMNIROUTE_API_KEY env ou None)
        timeout_seconds: Timeout HTTP

    Returns:
        OmniRouteAdapter configurado
    """
    from olympus.routing.omniroute_adapter import OmniRouteAdapter

    url = base_url or os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128")
    key = api_key or os.getenv("OLYMPUS_OMNIROUTE_API_KEY") or os.getenv("OMNIROUTE_API_KEY")
    return OmniRouteAdapter(
        base_url=url,
        api_key=key,
        timeout_seconds=timeout_seconds,
    )


def build_pipeline(
    repo: RepositorioPersistencia,
    router: Optional[RoutingAdapter] = None,
) -> OlympusPipeline:
    """Constrói OlympusPipeline com componentes padrão."""
    classifier = TaskClassifier()
    registry = build_default_registry()
    engine = DecisionEngine(registry)

    return OlympusPipeline(
        classifier=classifier,
        registry=registry,
        engine=engine,
        repo=repo,
        router=router,
    )


def run_closed_loop(
    task_description: str,
    project_id: str = "closed-loop-demo",
    router: Optional[RoutingAdapter] = None,
    repo: Optional[RepositorioPersistencia] = None,
) -> ClosedLoopResult:
    """
    Executa o fluxo completo fechado: Task → Decision → Execution → Result.

    Args:
        task_description: Descrição da tarefa a executar
        project_id: ID do projeto (cria se não existir)
        router: RoutingAdapter opcional (se None, apenas decide sem executar)
        repo: RepositorioPersistencia opcional (default: SQLite em memória)

    Returns:
        ClosedLoopResult com todos os dados do fluxo
    """
    # Repository (SQLite em memória por default)
    if repo is None:
        repo = SQLiteDevRepository(":memory:")

    # Garantir que projeto existe
    if repo.obter_projeto(project_id) is None:
        repo.criar_projeto(name=project_id, description="Closed Loop Demo", product_type=None, complexity=None, status="active")

    # Pipeline com router injetado
    pipeline = build_pipeline(repo, router=router)

    # 1. Criar tarefa
    tarefa = Tarefa(
        id=f"task-{int(__import__('time').time() * 1000)}",
        projeto_id=project_id,
        descricao=task_description,
    )

    # 2. Iniciar execução
    execution_id = pipeline.iniciar_execucao(project_id)

    # 3. DECISION: processar_tarefa -> classificar + decidir + persistir
    decisao, decision_record_id = pipeline.processar_tarefa(tarefa, project_id, execution_id)

    # 4. EXECUTION: executar_decisao via RoutingAdapter (se injetado)
    execution_result: Optional[RoutingExecutionResult] = None
    if router is not None:
        execution_result = pipeline.executar_decisao(decisao, task_description)

    # 5. Finalizar execução
    pipeline.finalizar_execucao(execution_id, [decisao])

    # 6. Persistir resultado de execução (se houver router e resultado)
    if execution_result is not None and decisao.modelo_escolhido is not None:
        # Buscar decision_record_id do log/registro persistido
        # O decision_record_id foi retornado por processar_tarefa
        pipeline.registrar_resultado_execucao(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            execution_result=execution_result,
        )

    # 7. Construir resultado estruturado
    result = ClosedLoopResult(
        task=task_description,
        task_type=tarefa.tipo.value if tarefa.tipo is not None else "desconhecido",
        policy=pipeline._nome_politica(tarefa),
        selected_model=decisao.modelo_escolhido or "nenhum",
        decision_confidence=decisao.confianca,
        decision_reason=decisao.motivo,
        actual_model=execution_result.actual_model if execution_result else "não executado",
        provider=execution_result.provider if execution_result else "não executado",
        success=execution_result.success if execution_result else False,
        latency_ms=execution_result.latency_ms if execution_result else 0,
        cost=execution_result.cost if execution_result else 0.0,
        output=execution_result.output or execution_result.error if execution_result else "sem router: apenas decisão",
        correlation_id=execution_result.metadata.get("correlation_id") if execution_result and execution_result.metadata else None,
        metadata=execution_result.metadata if execution_result else None,
    )

    return result


def run_closed_loop_with_real_omniroute(
    task_description: str,
    project_id: str = "closed-loop-demo",
    repo: Optional[RepositorioPersistencia] = None,
) -> ClosedLoopResult:
    """
    Executa closed loop com OmniRoute real (requer servidor rodando).

    Args:
        task_description: Descrição da tarefa
        project_id: ID do projeto
        repo: RepositorioPersistencia opcional (default: SQLite em memória)

    Returns:
        ClosedLoopResult com execução real

    Requer:
        OmniRoute rodando em http://127.0.0.1:20128 (ou OMNIROUTE_BASE_URL)
        Opcional: OMNIROUTE_API_KEY para autenticação
    """
    adapter = build_omniroute_adapter()
    return run_closed_loop(task_description, project_id, router=adapter, repo=repo)


if __name__ == "__main__":
    # Demo simples sem execução real (apenas decisão)
    print("=" * 60)
    print("OLYMPUS CLOSED LOOP — Demo (sem OmniRoute real)")
    print("=" * 60)

    task = "Escreva uma função Python que calcule os números primos até 100."

    # Criar repo e projeto para demo
    repo = SQLiteDevRepository(":memory:")
    project_id = repo.criar_projeto(name="closed-loop-demo", description="Closed Loop Demo", product_type=None, complexity=None, status="active")

    result = run_closed_loop(task, project_id=project_id, repo=repo)

    print(f"Task: {result.task}")
    print(f"Task Type: {result.task_type}")
    print(f"Policy: {result.policy}")
    print(f"Selected Model: {result.selected_model}")
    print(f"Decision Confidence: {result.decision_confidence:.2f}")
    print(f"Decision Reason: {result.decision_reason}")
    print(f"Actual Model: {result.actual_model}")
    print(f"Provider: {result.provider}")
    print(f"Success: {result.success}")
    print(f"Latency: {result.latency_ms}ms")
    cost_str = f"${result.cost:.4f}" if result.cost is not None else "N/A"
    print(f"Cost: {cost_str}")
    print(f"Output: {result.output[:200]}..." if len(result.output) > 200 else f"Output: {result.output}")
    if result.correlation_id:
        print(f"Correlation ID: {result.correlation_id}")
    print("=" * 60)
    print("Para execução real: RUN_REAL_OMNIROUTE=1 python3 -m olympus.closed_loop")
    print("=" * 60)