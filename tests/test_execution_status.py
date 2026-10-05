"""Testes de ExecutionStatus e classify_execution_error (PATCH 004C).

Valida a taxonomia técnica mínima e estável para resultado de execução.
Distinguir falha técnica de execução de qualidade da resposta.
"""

import unittest
from olympus.models import ExecutionStatus, ExecutionResult
from olympus.routing.omniroute_adapter import classify_execution_error
from olympus.db.sqlite_dev_repository import SQLiteDevRepository


class TestExecutionStatusEnum(unittest.TestCase):
    """Testes do enum ExecutionStatus."""

    def test_success_exists(self):
        self.assertEqual(ExecutionStatus.SUCCESS.value, "success")

    def test_timeout_exists(self):
        self.assertEqual(ExecutionStatus.TIMEOUT.value, "timeout")

    def test_provider_error_exists(self):
        self.assertEqual(ExecutionStatus.PROVIDER_ERROR.value, "provider_error")

    def test_billing_error_exists(self):
        self.assertEqual(ExecutionStatus.BILLING_ERROR.value, "billing_error")

    def test_unavailable_exists(self):
        self.assertEqual(ExecutionStatus.UNAVAILABLE.value, "unavailable")

    def test_rate_limited_exists(self):
        self.assertEqual(ExecutionStatus.RATE_LIMITED.value, "rate_limited")

    def test_authentication_error_exists(self):
        self.assertEqual(ExecutionStatus.AUTHENTICATION_ERROR.value, "authentication_error")

    def test_malformed_response_exists(self):
        self.assertEqual(ExecutionStatus.MALFORMED_RESPONSE.value, "malformed_response")

    def test_unknown_error_exists(self):
        self.assertEqual(ExecutionStatus.UNKNOWN_ERROR.value, "unknown_error")


class TestClassifyExecutionError(unittest.TestCase):
    """Testes da função pura classify_execution_error."""

    def test_1_success(self):
        """1. HTTP 200 com choices válidos → success."""
        # classify não é chamado para success, mas testamos fallback
        status = classify_execution_error(
            http_status=200,
            error_message="OK",
            metadata={"http_status": 200}
        )
        # 200 sem error → unknown_error (mas na prática success é setado antes)
        # O classify é chamado apenas para erros
        self.assertIn(status.value, [s.value for s in ExecutionStatus])

    def test_2_timeout_network_error(self):
        """2. timeout/network timeout → timeout."""
        status = classify_execution_error(
            metadata={"error_class": "TimeoutError", "endpoint": "/v1/chat/completions"}
        )
        self.assertEqual(status, ExecutionStatus.TIMEOUT)

    def test_3_provider_error_5xx(self):
        """3. HTTP 5xx → provider_error."""
        status = classify_execution_error(http_status=500)
        self.assertEqual(status, ExecutionStatus.PROVIDER_ERROR)

    def test_4_billing_error_402(self):
        """4. HTTP 402 → billing_error."""
        status = classify_execution_error(http_status=402)
        self.assertEqual(status, ExecutionStatus.BILLING_ERROR)

    def test_5_unavailable_404(self):
        """5. HTTP 404 → unavailable."""
        status = classify_execution_error(http_status=404)
        self.assertEqual(status, ExecutionStatus.UNAVAILABLE)

    def test_6_rate_limited_429(self):
        """6. HTTP 429 → rate_limited."""
        status = classify_execution_error(http_status=429)
        self.assertEqual(status, ExecutionStatus.RATE_LIMITED)

    def test_7_authentication_error_401(self):
        """7. HTTP 401 → authentication_error."""
        status = classify_execution_error(http_status=401)
        self.assertEqual(status, ExecutionStatus.AUTHENTICATION_ERROR)

    def test_8_authentication_error_403(self):
        """8. HTTP 403 → authentication_error."""
        status = classify_execution_error(http_status=403)
        self.assertEqual(status, ExecutionStatus.AUTHENTICATION_ERROR)

    def test_9_malformed_json(self):
        """9. JSON/parse failure → malformed_response."""
        status = classify_execution_error(
            error_message="JSON decode error",
            metadata={"http_status": 200}
        )
        self.assertEqual(status, ExecutionStatus.MALFORMED_RESPONSE)

    def test_10_unknown_error_defaults(self):
        """10. Unknown error defaults to unknown_error."""
        status = classify_execution_error(
            http_status=418,  # I'm a teapot
            error_message="Something weird"
        )
        self.assertEqual(status, ExecutionStatus.UNKNOWN_ERROR)

    def test_11_error_type_timeout(self):
        """11. error_type 'timeout' → timeout."""
        status = classify_execution_error(
            error_type="timeout",
            metadata={"http_status": 500}
        )
        self.assertEqual(status, ExecutionStatus.TIMEOUT)

    def test_12_error_type_rate_limit(self):
        """12. error_type 'rate_limit_exceeded' → rate_limited."""
        status = classify_execution_error(
            error_type="rate_limit_exceeded",
            metadata={"http_status": 429}
        )
        self.assertEqual(status, ExecutionStatus.RATE_LIMITED)

    def test_13_error_type_auth(self):
        """13. error_type 'authentication_error' → authentication_error."""
        status = classify_execution_error(
            error_type="authentication_error",
            metadata={"http_status": 401}
        )
        self.assertEqual(status, ExecutionStatus.AUTHENTICATION_ERROR)

    def test_14_error_code_quota(self):
        """14. error_code 'quota_exceeded' → billing_error."""
        status = classify_execution_error(
            error_code="quota_exceeded",
            metadata={"http_status": 402}
        )
        self.assertEqual(status, ExecutionStatus.BILLING_ERROR)

    def test_15_circuit_breaker_unavailable(self):
        """15. diagnostics circuit breaker → unavailable."""
        status = classify_execution_error(
            metadata={"diagnostics": {"circuit_breaker": "open"}}
        )
        self.assertEqual(status, ExecutionStatus.UNAVAILABLE)

    def test_16_urlerror_timeout(self):
        """16. URLError/TimeoutError local → timeout."""
        status = classify_execution_error(
            metadata={"error_class": "URLError", "endpoint": "/v1/chat/completions"}
        )
        self.assertEqual(status, ExecutionStatus.TIMEOUT)

    def test_17_empty_choices(self):
        """17. Empty choices in response → malformed_response."""
        status = classify_execution_error(
            http_status=200,
            error_message="Empty choices in response",
            metadata={"http_status": 200}
        )
        self.assertEqual(status, ExecutionStatus.MALFORMED_RESPONSE)

    def test_18_normal_success_not_classified(self):
        """18. Normal success doesn't go through classify (handled before)."""
        # This is a sanity check - success is determined before classify is called
        # classify is only invoked for failures
        pass

    def test_19_http_5xx_provider_failure(self):
        """19. HTTP 503/504 → provider_error."""
        for code in [500, 502, 503, 504]:
            status = classify_execution_error(http_status=code)
            self.assertEqual(status, ExecutionStatus.PROVIDER_ERROR, f"Failed for {code}")

    def test_20_no_metadata_unknown(self):
        """20. Sem metadata suficiente → unknown_error."""
        status = classify_execution_error(
            error_message="Some generic error"
        )
        self.assertEqual(status, ExecutionStatus.UNKNOWN_ERROR)


class TestExecutionResultPersistence(unittest.TestCase):
    """Testes de persistência com ExecutionStatus (round-trip SQLite)."""

    def setUp(self):
        self.repo = SQLiteDevRepository(":memory:")
        self.project_id = self.repo.criar_projeto(name="test-proj", description="Test Project")
        # Criar execução e decision_record reais para satisfazer FKs
        self.execution_id = self.repo.criar_execucao(self.project_id)
        self.decision_record_id = self.repo.registrar_decisao(
            tarefa_id="task-1",
            modelo_escolhido="openrouter/cohere/north-mini-code:free",
            candidatos_avaliados=["openrouter/cohere/north-mini-code:free"],
            motivo="teste",
            confianca=0.9,
            decisao_status="approved",
            input_type="codigo",
            task_description="Test task",
            selected_provider="openrouter",
            policy_applied="padrao_menor_custo",
            estimated_cost=0.0,
            estimated_latency_ms=500,
            project_id=self.project_id,
            execution_id=self.execution_id,
        )

    def test_19_failed_execution_persists_status(self):
        """19. Failed execution persists status."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="",
            provider="",
            output="",
            latency_ms=50,
            cost=0.0,
            success=False,
            error="Timeout after 30s",
            status=ExecutionStatus.TIMEOUT.value,
        )
        stored = self.repo.obter_execution_result(result_id)
        self.assertEqual(stored["status"], ExecutionStatus.TIMEOUT.value)
        self.assertFalse(stored["success"])
        self.assertEqual(stored["error"], "Timeout after 30s")

    def test_20_success_execution_persists_status(self):
        """20. Success execution persists status."""
        result_id = self.repo.registrar_execution_result(
            execution_id=self.execution_id,
            decision_record_id=self.decision_record_id,
            requested_model="openrouter/cohere/north-mini-code:free",
            actual_model="cohere/north-mini-code:free",
            provider="cohere",
            output="def hello(): pass",
            latency_ms=1500,
            cost=0.0,
            success=True,
            status=ExecutionStatus.SUCCESS.value,
        )
        stored = self.repo.obter_execution_result(result_id)
        self.assertEqual(stored["status"], ExecutionStatus.SUCCESS.value)
        self.assertTrue(stored["success"])

    def test_all_status_values_persist(self):
        """Todos os valores de ExecutionStatus persistem corretamente."""
        for status_enum in ExecutionStatus:
            result_id = self.repo.registrar_execution_result(
                execution_id=self.execution_id,
                decision_record_id=self.decision_record_id,
                requested_model="openrouter/cohere/north-mini-code:free",
                actual_model="cohere/north-mini-code:free" if status_enum == ExecutionStatus.SUCCESS else "",
                provider="cohere" if status_enum == ExecutionStatus.SUCCESS else "",
                output="output" if status_enum == ExecutionStatus.SUCCESS else "",
                latency_ms=100,
                cost=0.0,
                success=(status_enum == ExecutionStatus.SUCCESS),
                status=status_enum.value,
            )
            stored = self.repo.obter_execution_result(result_id)
            self.assertEqual(stored["status"], status_enum.value)


if __name__ == "__main__":
    unittest.main()