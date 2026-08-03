from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline

registry = ModelRegistry()
registry.registrar(Modelo(
    id="gpt-4o", nome="GPT-4o", provedor="openai",
    capacidades=[TaskType.CODIGO, TaskType.ARQUITETURA, TaskType.REVISAO, TaskType.RESPOSTA_LONGA],
    custo_estimado=8.0, latencia_estimada=2.5, confiabilidade=0.93, prioridade=2,
))
registry.registrar(Modelo(
    id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
    capacidades=[TaskType.CODIGO, TaskType.TEXTO, TaskType.RESPOSTA_CURTA, TaskType.DOCUMENTACAO],
    custo_estimado=1.0, latencia_estimada=0.9, confiabilidade=0.81, prioridade=1,
))
registry.registrar(Modelo(
    id="claude-sonnet", nome="Claude Sonnet", provedor="anthropic",
    capacidades=[TaskType.CODIGO, TaskType.ARQUITETURA, TaskType.REVISAO, TaskType.TESTES, TaskType.RESPOSTA_LONGA],
    custo_estimado=6.0, latencia_estimada=1.8, confiabilidade=0.95, prioridade=3,
))

classifier = TaskClassifier()
engine = DecisionEngine(registry)
repo = SQLiteDevRepository()  # troque por PostgresRepository(session) em produção — mesma interface
pipeline = OlympusPipeline(classifier, registry, engine, repo)

project_id = repo.criar_projeto(name="Projeto Demo", product_type="backend", complexity="media")
execution_id = pipeline.iniciar_execucao(project_id)

tarefas = [
    Tarefa(id="t1", projeto_id=project_id, descricao="Implementar função de autenticação com JWT no backend"),
    Tarefa(id="t2", projeto_id=project_id, descricao="Corrigir bug crítico em processamento de pagamento",
           critica=True, limite_custo=2.0),
]

decisoes = []
for tarefa in tarefas:
    decisao, decision_record_id = pipeline.processar_tarefa(tarefa, project_id, execution_id)
    decisoes.append(decisao)
    print(f"[{tarefa.id}] modelo={decisao.modelo_escolhido} status={decisao.decisao_status} "
          f"custo={decisao.custo_estimado} latencia_ms={decisao.latencia_estimada_ms} "
          f"decision_record_id={decision_record_id}")

# simula uma queda do provedor "anthropic" -> claude-sonnet fica indisponível para t3
registry.marcar_provedor_indisponivel("anthropic")
tarefa_t3 = Tarefa(id="t3", projeto_id=project_id, descricao="Revisar arquitetura do módulo de billing", critica=True)
decisao_t3, decision_record_id_t3 = pipeline.processar_tarefa(tarefa_t3, project_id, execution_id)
decisoes.append(decisao_t3)
print(f"[t3] modelo={decisao_t3.modelo_escolhido} status={decisao_t3.decisao_status} "
      f"custo={decisao_t3.custo_estimado} latencia_ms={decisao_t3.latencia_estimada_ms} "
      f"decision_record_id={decision_record_id_t3}")
registry.marcar_provedor_disponivel("anthropic")

pipeline.finalizar_execucao(execution_id, decisoes)

# ---- prova real: lê de volta do banco (não da memória) ----
print("\n--- Lendo de volta do banco (auditoria) ---")
cur = repo.conn.cursor()
cur.execute("SELECT status, total_cost, total_latency_ms, success_count, fallback_count, result_summary FROM execucoes WHERE id=?", (execution_id,))
print("Execução:", cur.fetchone())

cur.execute(
    "SELECT task_id, selected_model, status, decision_reason FROM decisao_registros WHERE execution_id=?",
    (execution_id,),
)
for row in cur.fetchall():
    print("Decisão:", row)

cur.execute("SELECT event_type, level, message FROM logs WHERE execution_id=?", (execution_id,))
for row in cur.fetchall():
    print("Log:", row)
