"""Testes de integração Pipeline × RoutingAdapter (PATCH 003A).

Valida que:
- Pipeline sem router mantém comportamento atual
- Pipeline aceita RoutingAdapter via dependency injection
- DECISION (processar_tarefa) e EXECUTION (executar_decisao) são separados
- Modelo selecionado pelo DecisionEngine é exatamente o recebido pelo router
- Todos os campos do RoutingExecutionResult são preservados
- Erro de execução não altera a decisão original
- Pipeline não importa OmniRouteAdapter
- FakeRoutingAdapter satisfaz RoutingAdapter
"""

import unittest
from typing import Optional

from olympus.models import (
    Tarefa,
    Modelo,
    TaskType,
    DecisaoRegistro,
    Prioridade,
)
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.interfaces import RepositorioPersistencia
from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
    ModelCapability,
)
from olympus.pipeline import OlympusPipeline


class FakeRoutingAdapter:
    """Fake implementation of RoutingAdapter for testing."""

    def __init__(self):
        self._models = [
            RoutingModelInfo(
                model_id="gpt-4o-mini",
                provider="openai",
                capabilities=[ModelCapability.CODIGO, ModelCapability.TEXTO],
                available=True,
                metadata={"version": "2024-07"},
            ),
            RoutingModelInfo(
                model_id="claude-sonnet-4",
                provider="anthropic",
                capabilities=[ModelCapability.ARQUITETURA, ModelCapability.CODIGO],
                available=True,
                metadata={"version": "2025-01"},
            ),
            RoutingModelInfo(
                model_id="auto/coding:free",
                provider="combo",
                capabilities=[ModelCapability.TESTES, ModelCapability.ARQUITETURA],
                available=True,
                metadata={"alias": True},
            ),
            RoutingModelInfo(
                model_id="openrouter/google/gemini-2.5-pro",
                provider="openrouter",
                capabilities=[ModelCapability.IMAGEM, ModelCapability.TESTES, ModelCapability.ARQUITETURA],
                available=True,
                metadata={},
            ),
        ]
        self._healthy = True
        self._execute_results = {}

    def list_models(self) -> list[RoutingModelInfo]:
        return list(self._models)

    def health(self) -> RoutingHealth:
        return RoutingHealth(
            healthy=self._healthy,
            provider="multi",
            status="operational" if self._healthy else "degraded",
            metadata={"models_count": len(self._models)},
        )

    def set_execute_result(self, model_id: str, result: RoutingExecutionResult):
        self._execute_results[model_id] = result

    def execute(
        self,
        model_id: str,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> RoutingExecutionResult:
        # Allow pre-configured results for specific models
        if model_id in self._execute_results:
            return self._execute_results[model_id]

        # Find the model
        model = next((m for m in self._models if m.model_id == model_id), None)
        if model is None:
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model="",
                provider="",
                output="",
                latency_ms=0,
                cost=0.0,
                success=False,
                error=f"Model {model_id} not found",
            )

        if not model.available:
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model=model_id,
                provider=model.provider,
                output="",
                latency_ms=0,
                cost=0.0,
                success=False,
                error=f"Model {model_id} unavailable",
            )

        # Simulate successful execution
        return RoutingExecutionResult(
            requested_model=model_id,
            actual_model=model_id,
            provider=model.provider,
            output=f"Fake response for: {prompt[:50]}",
            latency_ms=150,
            cost=0.002,
            success=True,
            metadata={"tokens_used": len(prompt) // 4},
        )


class FakeRepository(RepositorioPersistencia):
    """Fake repository for testing."""

    def __init__(self):
        self.projects = {}
        self.executions = {}
        self.decisions = {}
        self.logs = []
        self._committed = False

    def criar_projeto(self, project_id: str, nome: str, descricao: str = "") -> str:
        self.projects[project_id] = {"id": project_id, "nome": nome, "descricao": descricao}
        return project_id

    def obter_projeto(self, project_id: str):
        return self.projects.get(project_id)

    def criar_execucao(self, project_id: str) -> str:
        exec_id = f"exec_{len(self.executions) + 1}"
        self.executions[exec_id] = {"id": exec_id, "project_id": project_id, "status": "running"}
        return exec_id

    def registrar_decisao(self, **kwargs) -> str:
        decision_id = f"dec_{len(self.decisions) + 1}"
        self.decisions[decision_id] = kwargs
        return decision_id

    def registrar_log(self, **kwargs) -> None:
        self.logs.append(kwargs)

    def finalizar_execucao(self, execution_id: str, **kwargs) -> None:
        if execution_id in self.executions:
            self.executions[execution_id].update(kwargs)

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        pass


class FakeClassifier(TaskClassifier):
    """Fake classifier for testing."""

    def __init__(self, fixed_type: Optional[TaskType] = None):
        self._fixed_type = fixed_type

    def classify(self, descricao: str) -> TaskType:
        if self._fixed_type:
            return self._fixed_type
        # Simple keyword-based classification
        if "test" in descricao.lower() or "teste" in descricao.lower():
            return TaskType.TESTES
        if "arquitetura" in descricao.lower() or "architect" in descricao.lower():
            return TaskType.ARQUITETURA
        if "codigo" in descricao.lower() or "code" in descricao.lower():
            return TaskType.CODIGO
        return TaskType.TEXTO


class TestPipelineRoutingIntegration(unittest.TestCase):
    """Testes de integração do Pipeline com RoutingAdapter."""

    def setUp(self):
        self.repo = FakeRepository()
        self.classifier = FakeClassifier()  # dynamic classification
        self.registry = ModelRegistry()
        self.repo.criar_projeto("proj-1", "Test Project")

        # Registrar modelos no registry
        self.registry.registrar(Modelo(
            id="gpt-4o-mini",
            nome="GPT-4o Mini",
            provedor="openai",
            capacidades=[TaskType.CODIGO, TaskType.TEXTO],
            custo_estimado=0.001,
            latencia_estimada=0.5,
            confiabilidade=0.95,
        ))
        self.registry.registrar(Modelo(
            id="claude-sonnet-4",
            nome="Claude Sonnet 4",
            provedor="anthropic",
            capacidades=[TaskType.ARQUITETURA, TaskType.CODIGO],
            custo_estimado=0.01,
            latencia_estimada=1.0,
            confiabilidade=0.98,
        ))
        self.registry.registrar(Modelo(
            id="auto/coding:free",
            nome="Auto Coding Free",
            provedor="combo",
            capacidades=[TaskType.TESTES, TaskType.ARQUITETURA, TaskType.CODIGO],
            custo_estimado=0.0,
            latencia_estimada=0.3,
            confiabilidade=0.90,
        ))

        self.engine = DecisionEngine(self.registry)

        # Registrar modelos no registry
        self.registry.registrar(Modelo(
            id="gpt-4o-mini",
            nome="GPT-4o Mini",
            provedor="openai",
            capacidades=[TaskType.CODIGO, TaskType.TEXTO],
            custo_estimado=0.001,
            latencia_estimada=0.5,
            confiabilidade=0.95,
        ))
        self.registry.registrar(Modelo(
            id="claude-sonnet-4",
            nome="Claude Sonnet 4",
            provedor="anthropic",
            capacidades=[TaskType.ARQUITETURA, TaskType.CODIGO],
            custo_estimado=0.01,
            latencia_estimada=1.0,
            confiabilidade=0.98,
        ))
        self.registry.registrar(Modelo(
            id="auto/coding:free",
            nome="Auto Coding Free",
            provedor="combo",
            capacidades=[TaskType.TESTES, TaskType.ARQUITETURA, TaskType.CODIGO],
            custo_estimado=0.0,
            latencia_estimada=0.3,
            confiabilidade=0.90,
        ))

        self.engine = DecisionEngine(self.registry)

    def test_pipeline_without_router_maintains_current_behavior(self):
        """1. Pipeline sem router mantém comportamento atual."""
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=None,  # Sem router
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, decision_record_id = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        # Deve funcionar normalmente - decisão produzida
        self.assertIsNotNone(decisao)
        self.assertIsNotNone(decisao.modelo_escolhido)
        # auto/coding:free tem custo 0.0, então é escolhido para tarefa padrão CODIGO
        self.assertEqual(decisao.modelo_escolhido, "auto/coding:free")
        self.assertIsNotNone(decision_record_id)

        # executar_decisao deve retornar None sem router
        result = pipeline.executar_decisao(decisao, "Test prompt")
        self.assertIsNone(result)

    def test_pipeline_accepts_routing_adapter(self):
        """2. Pipeline aceita RoutingAdapter via dependency injection."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        self.assertIs(pipeline.router, router)
        self.assertIsInstance(pipeline.router, RoutingAdapter)

    def test_pipeline_executes_router_when_explicitly_enabled(self):
        """3. Pipeline executa router quando explicitamente habilitado via método."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        # Chamada explícita para execução
        result = pipeline.executar_decisao(decisao, "Test prompt")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, RoutingExecutionResult)

    def test_selected_model_from_decision_engine_passed_to_router(self):
        """4. Modelo selecionado pelo DecisionEngine é exatamente o recebido pelo router."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        # Verificar que o modelo decidido é auto/coding:free (custo 0.0 para CODIGO)
        self.assertEqual(decisao.modelo_escolhido, "auto/coding:free")

        result = pipeline.executar_decisao(decisao, "Test prompt")

        # O requested_model no resultado deve ser exatamente o modelo decidido
        self.assertEqual(result.requested_model, "auto/coding:free")
        self.assertEqual(result.actual_model, "auto/coding:free")

    def test_output_of_routing_execution_result_returns_to_caller(self):
        """5. Output do RoutingExecutionResult retorna ao caller."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        result = pipeline.executar_decisao(decisao, "Test prompt")

        self.assertIsNotNone(result.output)
        self.assertIn("Test prompt", result.output)

    def test_actual_model_preserved(self):
        """6. actual_model é preservado."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        result = pipeline.executar_decisao(decisao, "Test prompt")

        self.assertEqual(result.actual_model, "auto/coding:free")
        self.assertEqual(result.requested_model, result.actual_model)

    def test_provider_preserved(self):
        """7. provider é preservado."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        result = pipeline.executar_decisao(decisao, "Test prompt")

        # auto/coding:free tem provider "combo"
        self.assertEqual(result.provider, "combo")

    def test_latency_ms_preserved(self):
        """8. latency_ms é preservado."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        result = pipeline.executar_decisao(decisao, "Test prompt")

        self.assertIsInstance(result.latency_ms, int)
        self.assertGreater(result.latency_ms, 0)

    def test_cost_preserved(self):
        """9. cost é preservado."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        result = pipeline.executar_decisao(decisao, "Test prompt")

        self.assertIsInstance(result.cost, float)
        self.assertGreaterEqual(result.cost, 0.0)

    def test_execution_error_does_not_alter_original_decision(self):
        """10. Erro de execução não altera a decisão original."""
        router = FakeRoutingAdapter()

        # Configurar erro de execução para o modelo (auto/coding:free tem custo 0.0)
        error_result = RoutingExecutionResult(
            requested_model="auto/coding:free",
            actual_model="",
            provider="",
            output="",
            latency_ms=50,
            cost=0.0,
            success=False,
            error="Network error: Connection refused",
            metadata={"error_class": "URLError"},
        )
        router.set_execute_result("auto/coding:free", error_result)

        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, decision_record_id = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        # Guardar decisão original
        original_model = decisao.modelo_escolhido
        original_motivo = decisao.motivo
        original_status = decisao.decisao_status

        # Executar - deve falhar
        result = pipeline.executar_decisao(decisao, "Test prompt")

        # Verificar que a decisão NÃO foi alterada
        self.assertEqual(decisao.modelo_escolhido, original_model)
        self.assertEqual(decisao.motivo, original_motivo)
        self.assertEqual(decisao.decisao_status, original_status)

        # Verificar resultado de execução falhou
        self.assertFalse(result.success)
        self.assertIn("Network error", result.error)

    def test_pipeline_does_not_import_omniroute_adapter(self):
        """11. Pipeline não importa OmniRouteAdapter."""
        import olympus.pipeline as pipeline_module
        import olympus.routing.omniroute_adapter as omniroute_module

        # Verificar que pipeline não tem referência a OmniRouteAdapter
        pipeline_source = __import__("pathlib").Path(pipeline_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("OmniRouteAdapter", pipeline_source)
        self.assertNotIn("omniroute_adapter", pipeline_source)

        # Verificar que importa apenas interfaces
        self.assertIn("from olympus.routing.interfaces import", pipeline_source)
        self.assertIn("RoutingAdapter", pipeline_source)
        self.assertIn("RoutingExecutionResult", pipeline_source)

    def test_fake_routing_adapter_satisfies_routing_adapter(self):
        """12. FakeRoutingAdapter satisfaz RoutingAdapter (protocol compliance)."""
        adapter = FakeRoutingAdapter()
        self.assertIsInstance(adapter, RoutingAdapter)

        # Verificar métodos do protocolo
        models = adapter.list_models()
        self.assertIsInstance(models, list)
        self.assertTrue(all(isinstance(m, RoutingModelInfo) for m in models))

        health = adapter.health()
        self.assertIsInstance(health, RoutingHealth)

        result = adapter.execute("gpt-4o-mini", "test")
        self.assertIsInstance(result, RoutingExecutionResult)

    def test_existing_tests_remain_green(self):
        """13. Existing tests remain green - pipeline behavior unchanged without router."""
        # This test verifies that the existing test patterns still work
        # by running the same flow as before PATCH 003A

        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            # router=None (default, omitted)
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
            prioridade=Prioridade.QUALIDADE,
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, decision_record_id = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        # All existing assertions should pass
        self.assertIsNotNone(decisao)
        # auto/coding:free tem custo 0.0, então é escolhido para tarefa padrão CODIGO
        self.assertEqual(decisao.modelo_escolhido, "auto/coding:free")
        self.assertEqual(decisao.decisao_status, "approved")
        self.assertIsNotNone(decision_record_id)
        self.assertTrue(self.repo._committed is False)  # commit only on finalizar_execucao

        # Test with multiple tasks - tarefa crítica deve usar maior confiabilidade
        tarefa2 = Tarefa(
            id="task-2",
            projeto_id="proj-1",
            descricao="Arquitetura do sistema",
            critica=True,  # tarefa crítica -> política de confiabilidade
        )

        decisao2, _ = pipeline.processar_tarefa(tarefa2, "proj-1", exec_id)
        # ARQUITETURA crítica -> maior confiabilidade (claude-sonnet-4 tem 0.98 vs 0.90)
        self.assertEqual(decisao2.modelo_escolhido, "claude-sonnet-4")

        pipeline.finalizar_execucao(exec_id, [decisao, decisao2])
        self.assertTrue(self.repo._committed)

    def test_executar_decisao_returns_none_when_no_model_in_decision(self):
        """Verifica que executar_decisao retorna None quando decisão não tem modelo."""
        router = FakeRoutingAdapter()
        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        # Decisão sem modelo (simulada)
        decisao_sem_modelo = DecisaoRegistro(
            tarefa_id="task-x",
            modelo_escolhido=None,
            candidatos_avaliados=[],
            motivo="Nenhum modelo",
            fallback_usado=False,
            confianca=0.0,
        )

        result = pipeline.executar_decisao(decisao_sem_modelo, "Test")
        self.assertIsNone(result)

    def test_executar_decisao_passes_max_tokens_temperature(self):
        """Verifica que max_tokens e temperature são passados ao router."""
        router = FakeRoutingAdapter()
        captured = {}

        def capture_execute(model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
            if max_tokens is not None:
                captured["max_tokens"] = max_tokens
            if temperature is not None:
                captured["temperature"] = temperature
            return RoutingExecutionResult(
                requested_model=model_id,
                actual_model=model_id,
                provider="test",
                output="ok",
                latency_ms=10,
                cost=0.0,
                success=True,
            )

        router.execute = capture_execute

        pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=router,
        )

        tarefa = Tarefa(
            id="task-1",
            projeto_id="proj-1",
            descricao="Escreva uma função Python codigo",
        )

        exec_id = pipeline.iniciar_execucao("proj-1")
        decisao, _ = pipeline.processar_tarefa(tarefa, "proj-1", exec_id)

        pipeline.executar_decisao(decisao, "Test prompt", max_tokens=500, temperature=0.7)

        self.assertEqual(captured["max_tokens"], 500)
        self.assertEqual(captured["temperature"], 0.7)

        # Sem parâmetros opcionais
        captured.clear()
        pipeline.executar_decisao(decisao, "Test prompt")
        self.assertNotIn("max_tokens", captured)
        self.assertNotIn("temperature", captured)


if __name__ == "__main__":
    unittest.main()