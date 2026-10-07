import os
import tempfile
import time
from pathlib import Path

from olympus.agent.multibrain_registry import AgentModelRoute
from olympus.routing.capacity_fabric import CapacityAwareRoutingAdapter, CapacityFabric, capacity_filter_routes
from olympus.routing.interfaces import RoutingExecutionResult


class FakeAdapter:
    def __init__(self, results):
        self.results = list(results)
    def health(self):
        return None
    def list_models(self):
        return []
    def execute(self, model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
        return self.results.pop(0)


def result(*, success, status, error=None, provider="openrouter", actual="model", latency=25):
    return RoutingExecutionResult(
        requested_model="m", actual_model=actual, provider=provider, output="ok" if success else "",
        latency_ms=latency, cost=0.0, success=success, error=error, metadata={}, status=status,
    )


def setup_function(_):
    tmp = tempfile.NamedTemporaryFile(prefix="olympus-capacity-test-", suffix=".json", delete=False)
    tmp.close()
    Path(tmp.name).unlink(missing_ok=True)
    os.environ["OLYMPUS_CAPACITY_STATE_PATH"] = tmp.name
    os.environ["OLYMPUS_MODEL_COOLDOWN_SECONDS"] = "30"
    os.environ["OLYMPUS_TIMEOUT_CIRCUIT_THRESHOLD"] = "2"


def teardown_function(_):
    path = os.environ.pop("OLYMPUS_CAPACITY_STATE_PATH", "")
    if path:
        Path(path).unlink(missing_ok=True)


def test_rate_limit_opens_model_circuit_and_route_is_removed():
    fabric = CapacityFabric()
    fabric.observe(
        "openrouter::model-a",
        result(success=False, status="rate_limited", error="429 cooling down"),
        provider_hint="openrouter",
    )
    decision = fabric.decision("openrouter::model-a", "openrouter")
    assert decision.eligible is False
    assert decision.state == "cooldown"
    routes = (
        AgentModelRoute("openrouter::model-a", "a", "openrouter", 100),
        AgentModelRoute("groq::model-b", "b", "groq", 90),
    )
    filtered = capacity_filter_routes(routes)
    assert [r.id for r in filtered] == ["groq::model-b"]


def test_success_marks_route_ready_and_clears_cooldown():
    fabric = CapacityFabric()
    fabric.observe("groq::model-b", result(success=False, status="rate_limited", error="429", provider="groq"), provider_hint="groq")
    assert not fabric.decision("groq::model-b", "groq").eligible
    fabric.observe("groq::model-b", result(success=True, status="success", provider="groq", latency=8), provider_hint="groq")
    decision = fabric.decision("groq::model-b", "groq")
    assert decision.eligible
    assert decision.state == "ready"
    snap = fabric.snapshot()
    row = next(x for x in snap["routes"] if x["route_id"] == "groq::model-b")
    assert row["success_count"] == 1
    assert row["cooldown_until"] == 0.0


def test_repeated_timeout_only_opens_after_threshold():
    fabric = CapacityFabric()
    failure = result(success=False, status="technical_failure", error="Timeout: model did not respond", provider="openrouter")
    fabric.observe("openrouter::slow", failure, provider_hint="openrouter")
    assert fabric.decision("openrouter::slow", "openrouter").eligible
    fabric.observe("openrouter::slow", failure, provider_hint="openrouter")
    assert not fabric.decision("openrouter::slow", "openrouter").eligible


def test_qualification_requires_all_agent_route_v2_probes():
    fabric = CapacityFabric()
    probes = (
        "response",
        "action_protocol",
        "code_action",
        "patch_action",
        "repair_after_verifier",
    )
    for probe in probes[:-1]:
        row = fabric.record_probe("groq", "groq::m", probe, True, latency_ms=10)
        assert row["qualified"] is False
    row = fabric.record_probe("groq", "groq::m", probes[-1], True, latency_ms=10)
    assert row["qualified"] is True
    snap = fabric.snapshot()
    route = next(x for x in snap["routes"] if x["route_id"] == "groq::m")
    assert route["qualification_level"] == "agent_route_v2"


def test_old_agent_action_probe_set_does_not_claim_ready_agent():
    fabric = CapacityFabric()
    for probe in ("response", "action_protocol", "code_action"):
        row = fabric.record_probe("groq", "groq::legacy", probe, True, latency_ms=10)
    assert row["qualified"] is False


def test_capacity_adapter_records_execution_automatically():
    adapter = CapacityAwareRoutingAdapter(FakeAdapter([
        result(success=True, status="success", provider="openrouter", actual="upstream", latency=12)
    ]))
    got = adapter.execute("openrouter::model-a", "hello")
    assert got.success
    snap = CapacityFabric().snapshot()
    route = next(x for x in snap["routes"] if x["route_id"] == "openrouter::model-a")
    assert route["success_count"] == 1
    assert route["actual_model"] == "upstream"


def test_cloud_runtime_treats_rate_limit_and_open_circuit_as_capacity():
    from olympus.cloud.runtime import CloudRuntime
    assert CloudRuntime._is_capacity_error("rate_limited: all credentials cooling down")
    assert CloudRuntime._is_capacity_error("capacity_circuit_open: model_circuit_open")


def test_default_free_attempt_budget_is_six_when_no_saved_policy():
    from app.core.provider_runtime import routing_policy
    with tempfile.TemporaryDirectory() as directory:
        previous = os.environ.get("OLYMPUS_PROVIDER_SETTINGS_PATH")
        os.environ["OLYMPUS_PROVIDER_SETTINGS_PATH"] = str(Path(directory) / "settings.json")
        try:
            assert routing_policy().free_attempt_limit == 6
        finally:
            if previous is None:
                os.environ.pop("OLYMPUS_PROVIDER_SETTINGS_PATH", None)
            else:
                os.environ["OLYMPUS_PROVIDER_SETTINGS_PATH"] = previous
