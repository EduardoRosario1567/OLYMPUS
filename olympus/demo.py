from olympus.models import Modelo, Tarefa, TaskType, Prioridade
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine

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
registry.registrar(Modelo(
    id="claude-haiku", nome="Claude Haiku", provedor="anthropic",
    capacidades=[TaskType.TEXTO, TaskType.RESPOSTA_CURTA, TaskType.DOCUMENTACAO],
    custo_estimado=0.5, latencia_estimada=0.5, confiabilidade=0.70, prioridade=1,
))
registry.registrar(Modelo(
    id="modelo-experimental", nome="Modelo Experimental", provedor="startup-x",
    capacidades=[TaskType.INTEGRACAO],
    custo_estimado=0.3, latencia_estimada=0.4, confiabilidade=0.55, prioridade=0,
))

classifier = TaskClassifier()
engine = DecisionEngine(registry)

casos = [
    {
        "id": "t1", "descricao": "Implementar função de autenticação com JWT no backend",
        "critica": False, "urgente": False,
    },
    {
        "id": "t2", "descricao": "Definir a arquitetura de filas para processar picos de tráfego",
        "critica": True, "urgente": False,
    },
    {
        "id": "t3", "descricao": "Corrigir bug urgente em produção no endpoint de pagamento",
        "critica": True, "urgente": True,
    },
    {
        "id": "t4", "descricao": "Ok",
        "critica": False, "urgente": False,
    },
    {
        "id": "t5", "descricao": "Integrar com a API externa de pagamentos via webhook",
        "critica": False, "urgente": False,
    },
    {
        # tarefa crítica de código normalmente pegaria claude-sonnet (custo 6.0, mais confiável),
        # mas o limite é 2.0 -> deve dar downgrade para gpt-4o-mini (custo 1.0, confiabilidade 0.81)
        "id": "t6", "descricao": "Implementar função crítica de processamento de pagamento",
        "critica": True, "urgente": False, "limite_custo": 2.0,
    },
    {
        # limite tão baixo que nenhum candidato confiável cabe -> mantém o original com alerta
        "id": "t7", "descricao": "Revisar arquitetura do módulo de pagamentos",
        "critica": True, "urgente": False, "limite_custo": 0.1,
    },
]

for c in casos:
    tarefa = Tarefa(id=c["id"], projeto_id="proj-1", descricao=c["descricao"],
                     critica=c["critica"], urgente=c["urgente"],
                     limite_custo=c.get("limite_custo"))
    tarefa.tipo = classifier.classify(tarefa.descricao)
    decisao = engine.decidir(tarefa)

    print(f"\n--- Tarefa {tarefa.id} ---")
    print(f"Descrição: {tarefa.descricao}")
    print(f"Tipo classificado: {tarefa.tipo.value}")
    print(f"Candidatos avaliados (em ordem): {decisao.candidatos_avaliados}")
    print(f"Modelo escolhido: {decisao.modelo_escolhido}")
    print(f"Fallback usado: {decisao.fallback_usado}")
    print(f"Downgrade usado: {decisao.downgrade_usado}")
    print(f"Status da decisão: {decisao.decisao_status}")
    print(f"Motivo: {decisao.motivo}")

# --- caso extra: provedor indisponível -> alternativa compatível ---
registry.marcar_provedor_indisponivel("anthropic")
tarefa_t8 = Tarefa(id="t8", projeto_id="proj-1",
                    descricao="Definir arquitetura de cache distribuído para o checkout", critica=True)
tarefa_t8.tipo = classifier.classify(tarefa_t8.descricao)
decisao_t8 = engine.decidir(tarefa_t8)
print(f"\n--- Tarefa {tarefa_t8.id} (provedor anthropic indisponível) ---")
print(f"Descrição: {tarefa_t8.descricao}")
print(f"Tipo classificado: {tarefa_t8.tipo.value}")
print(f"Candidatos avaliados (em ordem): {decisao_t8.candidatos_avaliados}")
print(f"Modelo escolhido: {decisao_t8.modelo_escolhido}")
print(f"Fallback usado: {decisao_t8.fallback_usado}")
print(f"Status da decisão: {decisao_t8.decisao_status}")
print(f"Motivo: {decisao_t8.motivo}")
registry.marcar_provedor_disponivel("anthropic")
