"""Testes de QualityEvaluation — PATCH 005D.

Valida persistência de avaliação de qualidade.
Zero dependências externas, zero chamadas de rede/LLM.
"""

import json
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from olympus.models import QualityEvaluation
from olympus.db.sqlite_dev_repository import SQLiteDevRepository
from olympus.db.interfaces import RepositorioPersistencia


class TestQualityEvaluationModel(unittest.TestCase):
    """Testes da entidade QualityEvaluation (in-memory)."""

    def test_1_construction(self):
        """1. QualityEvaluation construction com todos os campos."""
        eval_obj = QualityEvaluation(
            id="eval-123",
            execution_result_id="exec-456",
            quality_score=0.85,
            passed=True,
            evaluator="rule_based",
            reason="Output passou nas checagens básicas",
            criteria={"non_empty_output": 1.0, "minimum_content": 1.0, "expected_structure": 1.0},
            metadata={"signal_weights": {"expected_structure": 2.0}, "policy_threshold": 0.6},
        )
        self.assertEqual(eval_obj.id, "eval-123")
        self.assertEqual(eval_obj.execution_result_id, "exec-456")
        self.assertEqual(eval_obj.quality_score, 0.85)
        self.assertTrue(eval_obj.passed)
        self.assertEqual(eval_obj.evaluator, "rule_based")
        self.assertEqual(eval_obj.reason, "Output passou nas checagens básicas")
        self.assertEqual(eval_obj.criteria, {"non_empty_output": 1.0, "minimum_content": 1.0, "expected_structure": 1.0})
        self.assertEqual(eval_obj.metadata, {"signal_weights": {"expected_structure": 2.0}, "policy_threshold": 0.6})

    def test_2_frozen_immutability(self):
        """2. QualityEvaluation é frozen (imutável)."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
        )
        # dataclass frozen=True impede mutação
        with self.assertRaises(FrozenInstanceError):
            eval_obj.quality_score = 0.9

    def test_3_quality_score_zero(self):
        """3. quality_score = 0 válido."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.0,
            passed=False,
            evaluator="rule_based",
            reason="completely incorrect",
            criteria={"correctness": 0.0},
        )
        self.assertEqual(eval_obj.quality_score, 0.0)
        self.assertFalse(eval_obj.passed)

    def test_4_quality_score_one(self):
        """4. quality_score = 1 válido."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=1.0,
            passed=True,
            evaluator="rule_based",
            reason="perfect",
            criteria={"correctness": 1.0},
        )
        self.assertEqual(eval_obj.quality_score, 1.0)
        self.assertTrue(eval_obj.passed)

    def test_5_quality_score_intermediate(self):
        """5. quality_score intermediário válido."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.75,
            passed=True,
            evaluator="code",
            reason="mostly correct",
            criteria={"correctness": 0.8, "style": 0.7},
        )
        self.assertEqual(eval_obj.quality_score, 0.75)
        self.assertTrue(eval_obj.passed)

    def test_6_quality_score_invalid_negative(self):
        """6. quality_score < 0 falha — validação na persistência, não no modelo."""
        # O modelo não valida — a validação é na persistência (CHECK constraint)
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=-0.1,
            passed=False,
            evaluator="test",
            reason="test",
        )
        self.assertEqual(eval_obj.quality_score, -0.1)

    def test_7_quality_score_invalid_above_one(self):
        """7. quality_score > 1 — modelo aceita, persistência bloqueia."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=1.1,
            passed=True,
            evaluator="test",
            reason="test",
        )
        self.assertEqual(eval_obj.quality_score, 1.1)

    def test_8_passed_true(self):
        """8. passed = True quando score >= threshold."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.8,
            passed=True,
            evaluator="rule_based",
            reason="passed",
        )
        self.assertTrue(eval_obj.passed)

    def test_9_passed_false(self):
        """9. passed = False quando score < threshold."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.3,
            passed=False,
            evaluator="rule_based",
            reason="failed",
        )
        self.assertFalse(eval_obj.passed)

    def test_10_evaluator_preserved(self):
        """10. evaluator string extensível preservada."""
        for evaluator in ["rule_based", "code", "text", "architecture", "llm", "human", "composite", "custom_xyz"]:
            eval_obj = QualityEvaluation(
                id="eval-1",
                execution_result_id="exec-1",
                quality_score=0.5,
                passed=False,
                evaluator=evaluator,
                reason="test",
            )
            self.assertEqual(eval_obj.evaluator, evaluator)

    def test_11_reason_preserved(self):
        """11. reason string preservada."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="Razão com acentos: ã, é, í, ó, ú",
        )
        self.assertEqual(eval_obj.reason, "Razão com acentos: ã, é, í, ó, ú")

    def test_12_criteria_preserved(self):
        """12. criteria dict arbitrário preservado."""
        criteria = {
            "correctness": 0.95,
            "completeness": 0.90,
            "relevance": 1.0,
            "custom_metric": 0.5,
        }
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.85,
            passed=True,
            evaluator="test",
            reason="good",
            criteria=criteria,
        )
        self.assertEqual(eval_obj.criteria, criteria)

    def test_13_metadata_preserved(self):
        """13. metadata dict arbitrário preservado."""
        metadata = {"evaluator_version": "1.0", "duration_ms": 150, "weights": {"correctness": 2.0}}
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
            metadata=metadata,
        )
        self.assertEqual(eval_obj.metadata, metadata)

    def test_14_execution_result_id_preserved(self):
        """14. execution_result_id preservado (FK)."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-result-123",
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
        )
        self.assertEqual(eval_obj.execution_result_id, "exec-result-123")

    def test_15_created_at_auto(self):
        """15. created_at preenchido automaticamente."""
        eval_obj = QualityEvaluation(
            id="eval-1",
            execution_result_id="exec-1",
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
        )
        # Verifica formato ISO
        dt = datetime.fromisoformat(eval_obj.created_at.replace('Z', '+00:00'))
        self.assertIsInstance(dt, datetime)


class TestQualityEvaluationSQLite(unittest.TestCase):
    """Testes de persistência SQLite."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        # Criar projeto e execução para FKs
        self.project_id = self.repo.criar_projeto(name="Test Project")
        self.execution_id = self.repo.criar_execucao(self.project_id)
        # Criar decision_record
        self.decision_id = self.repo.registrar_decisao(
            tarefa_id="task-1",
            modelo_escolhido="model-a",
            candidatos_avaliados=["model-a", "model-b"],
            motivo="test",
            confianca=0.9,
            decisao_status="approved",
            input_type="codigo",
            task_description="Test task",
            selected_provider="provider-a",
            policy_applied="padrao_menor_custo",
            estimated_cost=0.0,
            estimated_latency_ms=100,
            project_id=self.project_id,
            execution_id=self.execution_id,
        )
        # Criar execution_result
        self.execution_result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_id,
            requested_model="model-a",
            actual_model="model-a",
            provider="provider-a",
            output="def hello(): pass",
            latency_ms=1000,
            cost=0.0,
            success=True,
            status="success",
        )

    def test_16_sqlite_roundtrip(self):
        """16. SQLite round-trip completo."""
        eval_id = self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.85,
            passed=True,
            evaluator="rule_based",
            reason="Output passou nas checagens básicas",
            criteria={"non_empty_output": 1.0, "minimum_content": 1.0, "expected_structure": 1.0},
            metadata={"signal_weights": {"expected_structure": 2.0}, "policy_threshold": 0.6},
        )
        self.assertIsInstance(eval_id, str)
        self.assertTrue(len(eval_id) > 0)

        # Recuperar
        retrieved = self.repo.obter_quality_evaluation(eval_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["id"], eval_id)
        self.assertEqual(retrieved["execution_result_id"], self.execution_result_id)
        self.assertEqual(retrieved["quality_score"], 0.85)
        self.assertTrue(retrieved["passed"])
        self.assertEqual(retrieved["evaluator"], "rule_based")
        self.assertEqual(retrieved["reason"], "Output passou nas checagens básicas")
        self.assertEqual(retrieved["criteria"], {"non_empty_output": 1.0, "minimum_content": 1.0, "expected_structure": 1.0})
        self.assertEqual(retrieved["metadata"], {"signal_weights": {"expected_structure": 2.0}, "policy_threshold": 0.6})

    def test_17_unicode_reason(self):
        """17. Unicode reason preservado."""
        eval_id = self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="Razão com acentos: ã, é, í, ó, ú e emoji: 🎉",
        )
        retrieved = self.repo.obter_quality_evaluation(eval_id)
        self.assertEqual(retrieved["reason"], "Razão com acentos: ã, é, í, ó, ú e emoji: 🎉")

    def test_18_arbitrary_criteria_json(self):
        """18. Criteria JSON arbitrário."""
        criteria = {"custom_field": 0.7, "nested": {"a": 1, "b": 2}, "list": [1, 2, 3]}
        eval_id = self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
            criteria=criteria,
        )
        retrieved = self.repo.obter_quality_evaluation(eval_id)
        self.assertEqual(retrieved["criteria"], criteria)

    def test_19_arbitrary_metadata_json(self):
        """19. Metadata JSON arbitrário."""
        metadata = {"custom": "value", "weights": {"a": 1.5}, "array": [1, 2, 3]}
        eval_id = self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.5,
            passed=False,
            evaluator="test",
            reason="test",
            metadata=metadata,
        )
        retrieved = self.repo.obter_quality_evaluation(eval_id)
        self.assertEqual(retrieved["metadata"], metadata)

    def test_20_multiple_evaluations_same_execution_result(self):
        """20. Múltiplas avaliações podem referenciar mesmo execution_result."""
        eval_id1 = self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.8,
            passed=True,
            evaluator="rule_based",
            reason="first eval",
        )
        eval_id2 = self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.9,
            passed=True,
            evaluator="code",
            reason="second eval",
        )
        self.assertNotEqual(eval_id1, eval_id2)

        evals = self.repo.listar_quality_evaluations(execution_result_id=self.execution_result_id)
        self.assertEqual(len(evals), 2)

    def test_21_evaluation_does_not_modify_execution_result(self):
        """21. Avaliação não modifica ExecutionResult."""
        # Recuperar execution_result antes
        before = self.repo.obter_execution_result(self.execution_result_id)
        self.assertIsNotNone(before)

        # Persistir avaliação
        self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.8,
            passed=True,
            evaluator="rule_based",
            reason="test",
        )

        # Recuperar execution_result depois
        after = self.repo.obter_execution_result(self.execution_result_id)
        self.assertIsNotNone(after)
        # Verificar que campos principais não mudaram
        self.assertEqual(before["id"], after["id"])
        self.assertEqual(before["output"], after["output"])
        self.assertEqual(before["success"], after["success"])

    def test_22_listar_quality_evaluations_filter(self):
        """22. Lista com filtro por execution_result_id."""
        # Criar segundo execution_result
        exec_result_id_2 = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_id,
            requested_model="model-b",
            actual_model="model-b",
            provider="provider-b",
            output="output 2",
            latency_ms=500,
            cost=0.0,
            success=True,
            status="success",
        )

        # Avaliações em diferentes execution_results
        self.repo.registrar_quality_evaluation(
            execution_result_id=self.execution_result_id,
            quality_score=0.8,
            passed=True,
            evaluator="rule_based",
            reason="eval 1",
        )
        self.repo.registrar_quality_evaluation(
            execution_result_id=exec_result_id_2,
            quality_score=0.9,
            passed=True,
            evaluator="code",
            reason="eval 2",
        )

        # Filtrar pelo primeiro
        evals1 = self.repo.listar_quality_evaluations(execution_result_id=self.execution_result_id)
        self.assertEqual(len(evals1), 1)
        self.assertEqual(evals1[0]["execution_result_id"], self.execution_result_id)

        # Filtrar pelo segundo
        evals2 = self.repo.listar_quality_evaluations(execution_result_id=exec_result_id_2)
        self.assertEqual(len(evals2), 1)
        self.assertEqual(evals2[0]["execution_result_id"], exec_result_id_2)

        # Sem filtro
        all_evals = self.repo.listar_quality_evaluations()
        self.assertEqual(len(all_evals), 2)


class TestQualityEvaluationPipeline(unittest.TestCase):
    """Testes de integração com Pipeline."""

    def setUp(self):
        from olympus.pipeline import OlympusPipeline
        from olympus.classifier import TaskClassifier
        from olympus.registry import ModelRegistry
        from olympus.decision_engine import DecisionEngine
        from olympus.db.sqlite_dev_repository import SQLiteDevRepository
        from olympus.models import Modelo, TaskType

        self.repo = SQLiteDevRepository(":memory:")
        self.classifier = TaskClassifier()
        self.registry = ModelRegistry()
        # Registrar um modelo para CODIGO
        self.registry.registrar(Modelo(
            id="model-a",
            nome="Model A",
            provedor="provider-a",
            capacidades=[TaskType.CODIGO],
            custo_estimado=0.01,
            latencia_estimada=1.0,
            confiabilidade=0.9,
            prioridade=1,
            ativo=True,
        ))
        self.engine = DecisionEngine(self.registry)

        self.pipeline = OlympusPipeline(
            classifier=self.classifier,
            registry=self.registry,
            engine=self.engine,
            repo=self.repo,
            router=None,  # sem router — apenas persistência
        )

        self.project_id = self.repo.criar_projeto(name="Pipeline Test")

    def test_23_pipeline_explicit_persistence(self):
        """23. Pipeline oferece método explícito para persistir avaliação."""
        execution_id = self.pipeline.iniciar_execucao(self.project_id)

        from olympus.models import Tarefa, TaskType
        tarefa = Tarefa(
            id="task-1",
            projeto_id=self.project_id,
            descricao="Escreva uma função Python",
            tipo=TaskType.CODIGO,
        )

        decisao, decision_record_id = self.pipeline.processar_tarefa(tarefa, self.project_id, execution_id)
        self.assertIsNotNone(decision_record_id)

        # Simular execution_result (sem router real)
        execution_result_id = self.repo.registrar_execution_result(
            execution_id=execution_id,
            decision_record_id=decision_record_id,
            requested_model=decisao.modelo_escolhido,
            actual_model=decisao.modelo_escolhido,
            provider="provider-a",
            output="def hello(): pass",
            latency_ms=1000,
            cost=0.0,
            success=True,
            status="success",
        )

        # Persistir avaliação explicitamente via pipeline
        eval_id = self.pipeline.registrar_avaliacao_qualidade(
            execution_result_id=execution_result_id,
            quality_score=0.9,
            passed=True,
            evaluator="rule_based",
            reason="Output passou nas checagens básicas",
            criteria={"non_empty_output": 1.0, "minimum_content": 1.0, "expected_structure": 1.0},
            metadata={"signal_weights": {"expected_structure": 2.0}, "policy_threshold": 0.6},
        )

        self.assertIsNotNone(eval_id)

        # Verificar persistência
        retrieved = self.repo.obter_quality_evaluation(eval_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["quality_score"], 0.9)
        self.assertEqual(retrieved["evaluator"], "rule_based")

    def test_24_no_automatic_judge_invocation(self):
        """24. Pipeline NÃO invoca Judge automaticamente."""
        # Verificar que pipeline não tem lógica de seleção/invocação automática de Judge
        import olympus.pipeline as mod
        with open(mod.__file__) as f:
            source = f.read()
        # Não deve haver importação de JudgeAdapter no pipeline (fora de docstrings/comentários)
        # O pipeline apenas persiste avaliações, não invoca judges
        import_lines = [line for line in source.split('\n') if line.strip().startswith('from') or line.strip().startswith('import')]
        import_text = '\n'.join(import_lines)
        self.assertNotIn("from olympus.judge", import_text)
        self.assertNotIn("import olympus.judge", import_text)
        # Não deve haver instância de Judge no __init__ ou como atributo
        self.assertNotIn("self.judge", source)
        self.assertNotIn("judge =", source)


class TestQualityEvaluationPostgresORM(unittest.TestCase):
    """Testes da definição ORM Postgres (sem conexão real)."""

    def setUp(self):
        try:
            from olympus.db import models as db
            self.db = db
            self.has_sqlalchemy = True
        except ModuleNotFoundError:
            self.has_sqlalchemy = False

    def test_25_postgres_orm_definition(self):
        """25. QualityEvaluation ORM definido corretamente."""
        if not self.has_sqlalchemy:
            self.skipTest("SQLAlchemy não disponível no ambiente de teste")
        db = self.db

        # Verificar que a classe existe
        self.assertTrue(hasattr(db, "QualityEvaluation"))

        # Verificar campos principais
        qe = db.QualityEvaluation
        self.assertTrue(hasattr(qe, "__tablename__"))
        self.assertEqual(qe.__tablename__, "quality_evaluations")

        # Verificar colunas
        columns = {c.name for c in qe.__table__.columns}
        expected_columns = {
            "id", "execution_result_id", "quality_score", "passed",
            "evaluator", "reason", "criteria", "metadata", "created_at"
        }
        self.assertTrue(expected_columns.issubset(columns))

        # Verificar constraint de range (nome: ck_quality_score_range)
        constraints = [c for c in qe.__table__.constraints if hasattr(c, 'name') and c.name == 'ck_quality_score_range']
        self.assertTrue(len(constraints) > 0, "Constraint de qualidade (ck_quality_score_range) não encontrada")

    def test_26_orm_foreign_key(self):
        """26. FK para execution_results definida."""
        if not self.has_sqlalchemy:
            self.skipTest("SQLAlchemy não disponível no ambiente de teste")
        db = self.db
        qe = db.QualityEvaluation
        fk_columns = [c for c in qe.__table__.columns if c.foreign_keys]
        fk_targets = set()
        for c in fk_columns:
            for fk in c.foreign_keys:
                fk_targets.add(fk.column.table.name)
        self.assertIn("execution_results", fk_targets)


if __name__ == "__main__":
    unittest.main()