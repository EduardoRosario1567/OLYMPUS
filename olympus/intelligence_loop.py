"""
Intelligence Loop — PATCH 005E

Fecha o primeiro INTELLIGENCE LOOP real usando exclusivamente o RuleBasedJudge.

Fluxo:
Task
→ TaskClassifier
→ DecisionEngine
→ RoutingAdapter
→ OmniRouteAdapter
→ OmniRoute
→ modelo real
→ ExecutionResult
→ RuleBasedJudge
→ JudgeResult
→ QualityEvaluation persistence

Arquitetura:
- NÃO coloca Judge dentro do DecisionEngine
- NÃO coloca Judge dentro do OmniRouteAdapter
- NÃO coloca Judge automaticamente dentro do Pipeline
- Composição EXPLÍCITA:
  Pipeline → ExecutionResult → JudgeAdapter.evaluate() → Pipeline.registrar_avaliacao_qualidade()
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from olympus.classifier import TaskClassifier
from olympus.registry import ModelRegistry
from olympus.decision_engine import DecisionEngine
from olympus.pipeline import OlympusPipeline
from olympus.db.interfaces import RepositorioPersistencia
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.routing.interfaces import RoutingAdapter, RoutingExecutionResult
from olympus.models import Tarefa, TaskType, Modelo
from olympus.judge.interfaces import (
    JudgeAdapter,
    JudgeContext,
    JudgeResult,
    EvaluationPolicy,
)
from olympus.judge.rule_based import RuleBasedJudge
from olympus.judge.policies import default_codigo_policy, to_simple_policy


@dataclass
class IntelligenceLoopResult:
    """Resultado estruturado do fluxo completo de inteligência."""

    # Task
    task: str
    task_type: str

    # Decision
    decision: dict = field(default_factory=dict)

    # Execution
    execution: dict = field(default_factory=dict)

    # Evaluation
    evaluation: dict = field(default_factory=dict)

    # Persistence
    quality_evaluation_id: Optional[str] = None


def build_default_registry() -> ModelRegistry:
    """Constrói registry com modelos concretos para Intelligence Loop."""
    registry = ModelRegistry()

    # 1. Modelo principal: Cohere North Mini Code (gratuito, bom para coding/tool use)
    registry.registrar(Modelo(
        id="openrouter/cohere/north-mini-code:free",
        nome="Cohere North Mini Code (free)",
        provedor="openrouter",
        capacidades=[TaskType.CODIGO, TaskType.TESTES, TaskType.ARQUITETURA],
        custo_estimado=0.0,
        latencia_estimada=0.5,
        confiabilidade=0.85,
    ))

    # 2. Fallback: NVIDIA Nemotron 3.5 Lightning (gratuito, bom para coding)
    registry.registrar(Modelo(
        id="openrouter/nvidia/nemotron-3.5-lightning:free",
        nome="NVIDIA Nemotron 3.5 Lightning (free)",
        provedor="openrouter",
        capacidades=[TaskType.CODIGO, TaskType.TESTES, TaskType.ARQUITETURA],
        custo_estimado=0.0,
        latencia_estimada=0.6,
        confiabilidade=0.80,
    ))

    return registry


def build_omniroute_adapter(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> RoutingAdapter:
    """Constrói OmniRouteAdapter com configuração padrão."""
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


def build_judge(
    policy: Optional[EvaluationPolicy] = None,
) -> JudgeAdapter:
    """Constrói RuleBasedJudge com policy."""
    if policy is None:
        policy = to_simple_policy(default_codigo_policy())
    return RuleBasedJudge(policy=policy)


def build_judge_context(
    *,
    task_id: str,
    task_type: str,
    task_description: str,
    decision_id: str,
    decision_confidence: float,
    execution_result_id: str,
    requested_model: str,
    actual_model: str,
    provider: str,
    output: str,
    execution_status: str,
    metadata: Optional[dict] = None,
) -> JudgeContext:
    """Constrói JudgeContext a partir dos dados disponíveis."""
    return JudgeContext(
        task_id=task_id,
        task_type=task_type,
        task_description=task_description,
        decision_id=decision_id,
        decision_confidence=decision_confidence,
        execution_result_id=execution_result_id,
        requested_model=requested_model,
        actual_model=actual_model,
        provider=provider,
        output=output,
        execution_status=execution_status,
        metadata=metadata,
    )


def run_intelligence_loop(
    task_description: str,
    project_id: str = "intelligence-loop-demo",
    router: Optional[RoutingAdapter] = None,
    repo: Optional[RepositorioPersistencia] = None,
    judge: Optional[JudgeAdapter] = None,
    policy: Optional[EvaluationPolicy] = None,
) -> IntelligenceLoopResult:
    """
    Executa o fluxo completo de inteligência: Decision → Execution → Evaluation → Persistence.

    Args:
        task_description: Descrição da tarefa a executar
        project_id: ID do projeto (cria se não existir)
        router: RoutingAdapter opcional (se None, apenas decide sem executar)
        repo: RepositorioPersistencia opcional (default: SQLite em memória)
        judge: JudgeAdapter opcional (default: RuleBasedJudge com policy padrão)
        policy: EvaluationPolicy opcional para o judge

    Returns:
        IntelligenceLoopResult com todos os dados do fluxo agregados
    """
    # Repository (SQLite em memória por default)
    if repo is None:
        repo = SQLiteDevRepository(":memory:")

    # Garantir que projeto existe
    if repo.obter_projeto(project_id) is None:
        repo.criar_projeto(
            name=project_id,
            description="Intelligence Loop Demo",
            product_type=None,
            complexity=None,
            status="active"
        )

    # Pipeline com router injetado
    pipeline = build_pipeline(repo, router=router)

    # Judge (RuleBasedJudge por default)
    if judge is None:
        judge = build_judge(policy)

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
    execution_result_id: Optional[str] = None
    if execution_result is not None and decisao.modelo_escolhido is not None:
        execution_result_id = pipeline.registrar_resultado_execucao(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            execution_result=execution_result,
        )

    # 7. EVALUATION: RuleBasedJudge sobre o resultado de execução
    judge_result: Optional[JudgeResult] = None
    quality_evaluation_id: Optional[str] = None

    if execution_result is not None and execution_result_id is not None:
        # Construir JudgeContext
        context = build_judge_context(
            task_id=tarefa.id,
            task_type=tarefa.tipo.value if tarefa.tipo else "desconhecido",
            task_description=task_description,
            decision_id=decision_record_id,
            decision_confidence=decisao.confianca,
            execution_result_id=execution_result_id,
            requested_model=execution_result.requested_model,
            actual_model=execution_result.actual_model,
            provider=execution_result.provider,
            output=execution_result.output or "",
            execution_status=execution_result.status,
            metadata=execution_result.metadata,
        )

        # Executar Judge
        judge_result = judge.evaluate(context)

        # 8. PERSISTENCE: QualityEvaluation
        quality_evaluation_id = pipeline.registrar_avaliacao_qualidade(
            execution_result_id=execution_result_id,
            quality_score=judge_result.quality_score,
            passed=judge_result.passed,
            evaluator=judge_result.evaluator,
            reason=judge_result.reason,
            criteria=judge_result.criteria,
            metadata=judge_result.metadata,
        )

    # 9. Construir resultado estruturado agregado
    result = IntelligenceLoopResult(
        task=task_description,
        task_type=tarefa.tipo.value if tarefa.tipo is not None else "desconhecido",
        decision={
            "selected_model": decisao.modelo_escolhido or "nenhum",
            "confidence": decisao.confianca,
            "reason": decisao.motivo,
            "decision_record_id": decision_record_id,
        },
        execution={
            "requested_model": execution_result.requested_model if execution_result else "não executado",
            "actual_model": execution_result.actual_model if execution_result else "não executado",
            "provider": execution_result.provider if execution_result else "não executado",
            "status": execution_result.status if execution_result else "não executado",
            "success": execution_result.success if execution_result else False,
            "latency_ms": execution_result.latency_ms if execution_result else 0,
            "cost": execution_result.cost if execution_result else 0.0,
            "output": execution_result.output or execution_result.error if execution_result else "sem router: apenas decisão",
            "correlation_id": execution_result.metadata.get("correlation_id") if execution_result and execution_result.metadata else None,
            "execution_result_id": execution_result_id,
        },
        evaluation={
            "quality_score": judge_result.quality_score if judge_result else None,
            "passed": judge_result.passed if judge_result else None,
            "evaluator": judge_result.evaluator if judge_result else None,
            "reason": judge_result.reason if judge_result else None,
            "criteria": judge_result.criteria if judge_result else None,
        },
        quality_evaluation_id=quality_evaluation_id,
    )

    return result


def run_intelligence_loop_with_real_omniroute(
    task_description: str,
    project_id: str = "intelligence-loop-demo",
    repo: Optional[RepositorioPersistencia] = None,
    judge: Optional[JudgeAdapter] = None,
    policy: Optional[EvaluationPolicy] = None,
) -> IntelligenceLoopResult:
    """
    Executa intelligence loop com OmniRoute real (requer servidor rodando).

    Args:
        task_description: Descrição da tarefa
        project_id: ID do projeto
        repo: RepositorioPersistencia opcional (default: SQLite em memória)
        judge: JudgeAdapter opcional (default: RuleBasedJudge)
        policy: EvaluationPolicy opcional

    Returns:
        IntelligenceLoopResult com execução real

    Requer:
        OmniRoute rodando em http://127.0.0.1:20128 (ou OMNIROUTE_BASE_URL)
        Opcional: OMNIROUTE_API_KEY para autenticação
    """
    adapter = build_omniroute_adapter()
    return run_intelligence_loop(
        task_description=task_description,
        project_id=project_id,
        router=adapter,
        repo=repo,
        judge=judge,
        policy=policy,
    )


if __name__ == "__main__":
    # Demo simples sem execução real (apenas decisão)
    print("=" * 60)
    print("OLYMPUS INTELLIGENCE LOOP — Demo (sem OmniRoute real)")
    print("=" * 60)

    task = "Escreva uma função Python que calcule os números primos até 100."

    # Criar repo e projeto para demo
    repo = SQLiteDevRepository(":memory:")
    project_id = repo.criar_projeto(
        name="intelligence-loop-demo",
        description="Intelligence Loop Demo",
        product_type=None,
        complexity=None,
        status="active"
    )

    result = run_intelligence_loop(task, project_id=project_id, repo=repo)

    print(f"Task: {result.task}")
    print(f"Task Type: {result.task_type}")
    print(f"Decision: {result.decision}")
    print(f"Execution: {result.execution}")
    print(f"Evaluation: {result.evaluation}")
    print(f"Quality Evaluation ID: {result.quality_evaluation_id}")
    print("=" * 60)
    print("Para execução real: RUN_REAL_OMNIROUTE=1 python3 -m olympus.intelligence_loop")
    print("=" * 60)