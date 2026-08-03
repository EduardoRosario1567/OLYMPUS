"""Testes do núcleo (Fase 1) — classificador, registry, motor de decisão.
Roda com: python3 -m unittest tests.test_core -v
"""

import unittest

from olympus.models import Modelo, Tarefa, TaskType
from olympus.registry import ModelRegistry
from olympus.classifier import TaskClassifier
from olympus.decision_engine import DecisionEngine, SemModeloDisponivel


def registry_padrao() -> ModelRegistry:
    r = ModelRegistry()
    r.registrar(Modelo(
        id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
        capacidades=[TaskType.CODIGO, TaskType.TEXTO, TaskType.RESPOSTA_CURTA],
        custo_estimado=1.0, latencia_estimada=0.9, confiabilidade=0.81,
    ))
    r.registrar(Modelo(
        id="claude-sonnet", nome="Claude Sonnet", provedor="anthropic",
        capacidades=[TaskType.CODIGO, TaskType.ARQUITETURA],
        custo_estimado=6.0, latencia_estimada=1.8, confiabilidade=0.95,
    ))
    return r


class TestClassificador(unittest.TestCase):
    def test_classifica_codigo(self):
        c = TaskClassifier()
        self.assertEqual(c.classify("Implementar função de login"), TaskType.CODIGO)

    def test_classifica_resposta_curta(self):
        c = TaskClassifier()
        self.assertEqual(c.classify("Ok"), TaskType.RESPOSTA_CURTA)


class TestMotorDecisao(unittest.TestCase):
    def test_escolhe_mais_barato_em_tarefa_padrao(self):
        engine = DecisionEngine(registry_padrao())
        tarefa = Tarefa(id="t1", projeto_id="p1", descricao="x", tipo=TaskType.CODIGO)
        decisao = engine.decidir(tarefa)
        self.assertEqual(decisao.modelo_escolhido, "gpt-4o-mini")
        self.assertEqual(decisao.decisao_status, "approved")

    def test_escolhe_mais_confiavel_em_tarefa_critica(self):
        engine = DecisionEngine(registry_padrao())
        tarefa = Tarefa(id="t2", projeto_id="p1", descricao="x", tipo=TaskType.CODIGO, critica=True)
        decisao = engine.decidir(tarefa)
        self.assertEqual(decisao.modelo_escolhido, "claude-sonnet")

    def test_downgrade_por_limite_de_custo(self):
        engine = DecisionEngine(registry_padrao())
        tarefa = Tarefa(id="t3", projeto_id="p1", descricao="x", tipo=TaskType.CODIGO,
                         critica=True, limite_custo=2.0)
        decisao = engine.decidir(tarefa)
        self.assertEqual(decisao.modelo_escolhido, "gpt-4o-mini")
        self.assertTrue(decisao.downgrade_usado)
        self.assertEqual(decisao.decisao_status, "downgraded")

    def test_provedor_indisponivel_usa_alternativa(self):
        registry = registry_padrao()
        registry.marcar_provedor_indisponivel("anthropic")
        engine = DecisionEngine(registry)
        tarefa = Tarefa(id="t4", projeto_id="p1", descricao="x", tipo=TaskType.CODIGO, critica=True)
        decisao = engine.decidir(tarefa)
        self.assertEqual(decisao.modelo_escolhido, "gpt-4o-mini")
        self.assertTrue(decisao.fallback_usado)
        self.assertIn("indisponível", decisao.motivo)

    def test_sem_modelo_disponivel_levanta_excecao(self):
        engine = DecisionEngine(registry_padrao())
        tarefa = Tarefa(id="t5", projeto_id="p1", descricao="x", tipo=TaskType.IMAGEM)
        with self.assertRaises(SemModeloDisponivel):
            engine.decidir(tarefa)


if __name__ == "__main__":
    unittest.main()
