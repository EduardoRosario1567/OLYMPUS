from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline

registry = ModelRegistry()
registry.registrar(Modelo(
    id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
    capacidades=[TaskType.CODIGO], custo_estimado=1.0, latencia_estimada=0.9, confiabilidade=0.81,
))

classifier = TaskClassifier()
engine = DecisionEngine(registry)
repo = SQLiteDevRepository()
pipeline = OlympusPipeline(classifier, registry, engine, repo)

# --- dois projetos reais ---
proj_a = repo.criar_projeto(name="Checkout Revamp", product_type="e-commerce", complexity="alta")
proj_b = repo.criar_projeto(name="Billing Service", product_type="backend", complexity="media")

for proj_id, desc in [(proj_a, "Implementar carrinho de compras"), (proj_b, "Implementar cobrança recorrente")]:
    execution_id = pipeline.iniciar_execucao(proj_id)
    tarefa = Tarefa(id=f"t-{proj_id[:8]}", projeto_id=proj_id, descricao=desc)
    decisao, _ = pipeline.processar_tarefa(tarefa, proj_id, execution_id)
    pipeline.finalizar_execucao(execution_id, [decisao])

# --- projetos: listagem e leitura individual ---
projetos = repo.listar_projetos()
assert len(projetos) == 2
nomes = {p["name"] for p in projetos}
assert nomes == {"Checkout Revamp", "Billing Service"}

projeto_a_lido = repo.obter_projeto(proj_a)
assert projeto_a_lido["name"] == "Checkout Revamp"
assert repo.obter_projeto("id-inexistente") is None

# --- execuções: filtro por projeto isola de verdade ---
execucoes_a = repo.listar_execucoes(project_id=proj_a)
assert len(execucoes_a) == 1
assert execucoes_a[0]["project_id"] == proj_a
assert execucoes_a[0]["modelo_principal"] == "gpt-4o-mini"

execucoes_todas = repo.listar_execucoes()
assert len(execucoes_todas) == 2

execucoes_status_completed = repo.listar_execucoes(status="completed")
assert len(execucoes_status_completed) == 2

# --- logs: filtro por projeto e busca textual ---
logs_a = repo.listar_logs(project_id=proj_a)
assert len(logs_a) == 1
assert "gpt-4o-mini" in logs_a[0]["message"]

logs_busca = repo.listar_logs(busca="carrinho de compras")
# a busca é em message/event_type, não na descrição da tarefa -> não deve achar nada aqui
assert logs_busca == []

logs_busca_modelo = repo.listar_logs(busca="gpt-4o-mini")
assert len(logs_busca_modelo) == 2  # os dois logs citam o modelo na mensagem

print("OK — projetos, filtros de execução e busca de logs todos validados.")
