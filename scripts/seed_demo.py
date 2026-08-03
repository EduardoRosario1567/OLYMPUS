"""
Seed opcional de demonstração para a Alpha.

IMPORTANTE: isso não é "dado fake" disfarçado — cria projetos reais e roda
tarefas de verdade pelo classificador/motor de decisão/pipeline real,
gravando no MESMO banco que o backend usa (respeita OLYMPUS_SQLITE_PATH).
Sem isso, um primeiro acesso ao Olympus mostra tudo vazio (correto, mas
pouco demonstrável). Rodar isso é opcional e explícito — nunca acontece
sozinho no boot do backend.

Uso:
    export PYTHONPATH=.
    python3 scripts/seed_demo.py
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline

# Mesmo default ancorado que backend/app/core/deps.py usa — repo_root/olympus_dev.db.
# Antes, o default aqui era relativo ao CWD de quem chamava o script, o que podia
# apontar pra um arquivo diferente do que o backend estava lendo, sem erro visível.
DB_PATH = os.environ.get("OLYMPUS_SQLITE_PATH", os.path.join(REPO_ROOT, "olympus_dev.db"))


def main() -> None:
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
    repo = SQLiteDevRepository(DB_PATH)
    pipeline = OlympusPipeline(classifier, registry, engine, repo)

    projetos_existentes = repo.listar_projetos()
    if projetos_existentes:
        print(f"'{DB_PATH}' já tem {len(projetos_existentes)} projeto(s). Nada a fazer.")
        print("Apague o arquivo se quiser recomeçar do zero.")
        return

    projetos = [
        {
            "id": repo.criar_projeto(
                name="Checkout Revamp", product_type="e-commerce", complexity="alta",
                description="Reescrita do fluxo de checkout",
            ),
            "tarefas": [
                "Implementar carrinho de compras com persistência",
                "Corrigir bug crítico no cálculo de frete",
                "Revisar arquitetura do módulo de pagamento",
            ],
        },
        {
            "id": repo.criar_projeto(
                name="Billing Service", product_type="backend", complexity="media",
                description="Serviço de cobrança recorrente",
            ),
            "tarefas": [
                "Implementar endpoint de cobrança recorrente",
                "Escrever testes para o serviço de billing",
            ],
        },
    ]

    for i, projeto in enumerate(projetos):
        execution_id = pipeline.iniciar_execucao(projeto["id"])
        decisoes = []
        for j, desc in enumerate(projeto["tarefas"]):
            tarefa = Tarefa(id=f"seed-{i}-{j}", projeto_id=projeto["id"], descricao=desc)
            decisao, _ = pipeline.processar_tarefa(tarefa, projeto["id"], execution_id)
            decisoes.append(decisao)
        pipeline.finalizar_execucao(execution_id, decisoes)

    print(f"Seed concluído em '{DB_PATH}': 2 projetos, {sum(len(p['tarefas']) for p in projetos)} tarefas reais processadas.")


if __name__ == "__main__":
    main()
