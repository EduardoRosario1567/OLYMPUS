"""Testes dos services que os routers do FastAPI chamam.
FastAPI não está instalável neste ambiente (ver relatório), então isso é a
melhor aproximação real de "a API responde corretamente": exercita a MESMA
função que cada endpoint chama, com os MESMOS parâmetros que uma request
HTTP produziria.
Roda com: python3 -m unittest tests.test_services -v
"""

import unittest

from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline
from olympus.services.dashboard_service import montar_dashboard_summary
from olympus.services.projects_service import listar_projetos, obter_projeto
from olympus.services.executions_service import listar_execucoes, obter_execucao
from olympus.services.logs_service import listar_logs


class TestServices(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()
        self.registry.registrar(Modelo(
            id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
            capacidades=[TaskType.CODIGO], custo_estimado=1.0, latencia_estimada=0.9, confiabilidade=0.81,
        ))
        classifier = TaskClassifier()
        engine = DecisionEngine(self.registry)
        self.repo = SQLiteDevRepository()
        self.pipeline = OlympusPipeline(classifier, self.registry, engine, self.repo)

        self.pid = self.repo.criar_projeto(name="Projeto Teste")
        eid = self.pipeline.iniciar_execucao(self.pid)
        tarefa = Tarefa(id="t1", projeto_id=self.pid, descricao="Implementar endpoint")
        decisao, _ = self.pipeline.processar_tarefa(tarefa, self.pid, eid)
        self.pipeline.finalizar_execucao(eid, [decisao])
        self.eid = eid

    # equivalente a GET /dashboard/summary
    def test_dashboard_summary(self):
        resumo = montar_dashboard_summary(self.repo, self.registry)
        self.assertEqual(resumo.total_execucoes, 1)
        self.assertEqual(resumo.projetos.valor, 1)
        self.assertTrue(resumo.projetos.implementado)
        self.assertFalse(resumo.agentes.implementado)

    # equivalente a GET /projects e GET /projects/{id}
    def test_projects_endpoints(self):
        projetos = listar_projetos(self.repo)
        self.assertEqual(len(projetos), 1)
        projeto = obter_projeto(self.repo, self.pid)
        self.assertEqual(projeto["name"], "Projeto Teste")
        self.assertIsNone(obter_projeto(self.repo, "id-inexistente"))

    # equivalente a GET /executions e GET /executions/{id}
    def test_executions_endpoints(self):
        execucoes = listar_execucoes(self.repo, project_id=self.pid)
        self.assertEqual(len(execucoes), 1)
        execucao = obter_execucao(self.repo, self.eid)
        self.assertEqual(execucao["status"], "completed")
        self.assertIsNone(obter_execucao(self.repo, "id-inexistente"))

    # equivalente a GET /logs e GET /logs/search
    def test_logs_endpoints(self):
        logs = listar_logs(self.repo, execution_id=self.eid)
        self.assertEqual(len(logs), 1)
        busca = listar_logs(self.repo, busca="gpt-4o-mini")
        self.assertEqual(len(busca), 1)
        vazio = listar_logs(self.repo, busca="termo-que-nao-existe-em-nada")
        self.assertEqual(vazio, [])


if __name__ == "__main__":
    unittest.main()
