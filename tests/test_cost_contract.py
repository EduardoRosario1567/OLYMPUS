import unittest

from olympus.db.sqlite_dev_repository import SQLiteDevRepository


class TestCostContract(unittest.TestCase):

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(
            name="cost-contract",
            description="cost None regression",
        )
        self.execution_id = self.repo.criar_execucao(self.project_id)
        self.decision_id = self.repo.registrar_decisao(
            tarefa_id="task-1",
            modelo_escolhido="openrouter/cohere/north-mini-code:free",
            candidatos_avaliados=[],
            motivo="test",
            confianca=1.0,
            decisao_status="approved",
            input_type="codigo",
            task_description="test",
            selected_provider="openrouter",
            policy_applied="test",
            estimated_cost=0.0,
            estimated_latency_ms=1,
            project_id=self.project_id,
            execution_id=self.execution_id,
        )

    def tearDown(self):
        self.repo.close()

    def test_none_cost_is_persisted_as_zero(self):
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="",
            provider="",
            output="",
            latency_ms=1,
            cost=None,
            success=False,
            error="timeout",
            status="timeout",
        )
        result = self.repo.obter_execution_result(result_id)
        self.assertEqual(result["cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
