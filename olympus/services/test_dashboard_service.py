from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline
from olympus.services.dashboard_service import montar_dashboard_summary
from olympus.services.executions_service import listar_execucoes as listar_execucoes_recentes
from olympus.services.logs_service import listar_logs as listar_logs_recentes

registry = ModelRegistry()
registry.registrar(Modelo(
    id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
    capacidades=[TaskType.CODIGO, TaskType.TEXTO], custo_estimado=1.0,
    latencia_estimada=0.9, confiabilidade=0.81,
))
registry.registrar(Modelo(
    id="claude-sonnet", nome="Claude Sonnet", provedor="anthropic",
    capacidades=[TaskType.CODIGO], custo_estimado=6.0,
    latencia_estimada=1.8, confiabilidade=0.95,
))

classifier = TaskClassifier()
engine = DecisionEngine(registry)
repo = SQLiteDevRepository()
pipeline = OlympusPipeline(classifier, registry, engine, repo)

project_id = repo.criar_projeto(name="Projeto Teste")

# gpt-4o-mini vai ganhar 3x (deve virar "modelo mais usado"), claude-sonnet só via critica sem limite
for exec_num, descricoes in enumerate([
    ["Implementar função de login", "Corrigir bug no checkout"],
    ["Implementar endpoint de relatórios"],
], start=1):
    execution_id = pipeline.iniciar_execucao(project_id)
    decisoes = []
    for i, desc in enumerate(descricoes):
        tarefa = Tarefa(id=f"e{exec_num}-t{i}", projeto_id=project_id, descricao=desc)
        decisao, _ = pipeline.processar_tarefa(tarefa, project_id, execution_id)
        decisoes.append(decisao)
    pipeline.finalizar_execucao(execution_id, decisoes)

summary = montar_dashboard_summary(repo, registry)
execucoes = listar_execucoes_recentes(repo)
logs = listar_logs_recentes(repo)

print("summary:", summary)
print("\nexecucoes_recentes:")
for e in execucoes:
    print(" ", e)
print("\nlogs_recentes:")
for l in logs:
    print(" ", l)

assert summary.total_execucoes == 2
assert summary.total_modelos == 2
assert summary.total_decisoes == 3
assert summary.modelo_mais_usado == "gpt-4o-mini"
assert summary.projetos.implementado is True
assert summary.projetos.valor == 1  # o próprio project_id criado no início do teste
assert summary.agentes.implementado is False
assert len(execucoes) == 2
assert len(logs) == 3  # um log por decisão tomada
assert all(l["level"] == "info" for l in logs)  # nenhuma dessas teve fallback/downgrade
print("\nOK — todas as assertions passaram.")
