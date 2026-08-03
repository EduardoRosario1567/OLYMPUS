"""Testes de persistência — pipeline real gravando em SQLite de verdade.
Roda com: python3 -m unittest tests.test_persistence -v
"""

import unittest

from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.pipeline import OlympusPipeline


def montar_pipeline():
    registry = ModelRegistry()
    registry.registrar(Modelo(
        id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
        capacidades=[TaskType.CODIGO], custo_estimado=1.0, latencia_estimada=0.9, confiabilidade=0.81,
    ))
    classifier = TaskClassifier()
    engine = DecisionEngine(registry)
    repo = SQLiteDevRepository()  # :memory: — banco novo a cada teste
    pipeline = OlympusPipeline(classifier, registry, engine, repo)
    return repo, pipeline


class TestPersistencia(unittest.TestCase):
    def test_criar_projeto_e_ler_de_volta(self):
        repo, _ = montar_pipeline()
        pid = repo.criar_projeto(name="Projeto X")
        projeto = repo.obter_projeto(pid)
        self.assertEqual(projeto["name"], "Projeto X")

    def test_execucao_exige_projeto_existente(self):
        _, pipeline = montar_pipeline()
        with self.assertRaises(ValueError):
            pipeline.iniciar_execucao("id-que-nao-existe")

    def test_fk_de_execucao_e_respeitada_no_banco(self):
        repo, _ = montar_pipeline()
        with self.assertRaises(Exception):  # sqlite3.IntegrityError
            repo.conn.execute(
                "INSERT INTO execucoes (id, project_id, status, created_at, updated_at) "
                "VALUES ('x','id-que-nao-existe','pending','now','now')"
            )

    def test_pipeline_completo_grava_decisao_e_log(self):
        repo, pipeline = montar_pipeline()
        pid = repo.criar_projeto(name="Projeto Y")
        eid = pipeline.iniciar_execucao(pid)
        tarefa = Tarefa(id="t1", projeto_id=pid, descricao="Implementar login")
        decisao, decision_record_id = pipeline.processar_tarefa(tarefa, pid, eid)
        pipeline.finalizar_execucao(eid, [decisao])

        execucao = repo.obter_execucao(eid)
        self.assertEqual(execucao["status"], "completed")

        logs = repo.listar_logs(execution_id=eid)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["decision_record_id"], decision_record_id)

    def test_filtro_de_execucoes_por_projeto_isola_dados(self):
        repo, pipeline = montar_pipeline()
        pid_a = repo.criar_projeto(name="A")
        pid_b = repo.criar_projeto(name="B")
        for pid in (pid_a, pid_b):
            eid = pipeline.iniciar_execucao(pid)
            tarefa = Tarefa(id=f"t-{pid[:6]}", projeto_id=pid, descricao="Implementar algo")
            decisao, _ = pipeline.processar_tarefa(tarefa, pid, eid)
            pipeline.finalizar_execucao(eid, [decisao])

        execucoes_a = repo.listar_execucoes(project_id=pid_a)
        self.assertEqual(len(execucoes_a), 1)
        self.assertEqual(execucoes_a[0]["project_id"], pid_a)


if __name__ == "__main__":
    unittest.main()
