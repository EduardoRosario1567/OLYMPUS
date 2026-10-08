import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from olympus.agent.control_plane import AgentControlPlane
from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.agent.loop import AgentLoopResult
from olympus.agent.state import AgentState, AgentStatus
from olympus.routing.interfaces import RoutingExecutionResult, RoutingHealth, RoutingModelInfo, ModelCapability
from olympus.routing.provider_fabric import (
    MultiProviderRoutingAdapter,
    ProviderRegistry,
    provider_route_id,
    split_provider_route,
)


class FakeAdapter:
    def __init__(self, provider, result=None):
        self.provider = provider
        self.calls = []
        self.result = result

    def health(self):
        return RoutingHealth(True, self.provider, "healthy")

    def list_models(self):
        return [RoutingModelInfo("model-a", self.provider, [ModelCapability.CODIGO], True)]

    def execute(self, model_id, prompt, **kwargs):
        self.calls.append((model_id, prompt, kwargs))
        return self.result or RoutingExecutionResult(
            model_id, model_id, self.provider, "OK", 1, 0.0, True
        )


class ScriptedAdapter(FakeAdapter):
    def __init__(self, provider, outputs):
        super().__init__(provider)
        self.outputs = list(outputs)

    def execute(self, model_id, prompt, **kwargs):
        self.calls.append((model_id, prompt, kwargs))
        output = self.outputs.pop(0)
        return RoutingExecutionResult(model_id, model_id, self.provider, output, 1, 0.0, True)


class ProviderSelector:
    def select_candidates(self, task):
        return (
            "openrouter/openrouter/free",
            "groq::openai/gpt-oss-120b",
            "groq::openai/gpt-oss-20b",
            "cerebras::qwen-3.8-27b",
        )


class ProviderLoop:
    def __init__(self, model):
        self.model = model

    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        state = initial_state or AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
        if selected_model == "openrouter/openrouter/free":
            state = state.next_iteration().transition(
                AgentStatus.BLOCKED,
                files_modified=("app/index.html",),
                errors=("[429] Rate limit exceeded: free-models-per-day",),
                metadata={"failure_kind": "technical"},
            )
        elif selected_model.startswith("groq::"):
            self.assert_resumed(state)
            state = state.resume_for_model(selected_model).transition(AgentStatus.COMPLETED)
        else:
            self.assert_resumed(state)
            state = state.resume_for_model(selected_model).transition(AgentStatus.COMPLETED)
        return AgentLoopResult(state, ())

    @staticmethod
    def assert_resumed(state):
        assert state.files_modified == ("app/index.html",)


class GroqQuotaLoop(ProviderLoop):
    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        state = initial_state or AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
        if selected_model == "openrouter/openrouter/free":
            state = state.next_iteration().transition(
                AgentStatus.BLOCKED,
                errors=("timeout",),
                metadata={"failure_kind": "technical"},
            )
        elif selected_model == "groq::openai/gpt-oss-120b":
            state = state.resume_for_model(selected_model).transition(
                AgentStatus.BLOCKED,
                errors=("authentication_error: invalid api key",),
                metadata={"failure_kind": "technical"},
            )
        elif selected_model == "groq::openai/gpt-oss-20b":
            raise AssertionError("invalid provider credentials must skip its remaining models")
        else:
            state = state.resume_for_model(selected_model).transition(AgentStatus.COMPLETED)
        return AgentLoopResult(state, ())


class TestProviderFailoverV210(unittest.TestCase):
    def test_route_identity_round_trip(self):
        route = provider_route_id("groq", "openai/gpt-oss-120b")
        self.assertEqual(route, "groq::openai/gpt-oss-120b")
        self.assertEqual(split_provider_route(route, "omniroute"), ("groq", "openai/gpt-oss-120b"))
        self.assertEqual(split_provider_route("openrouter/openrouter/free", "omniroute"), ("omniroute", "openrouter/openrouter/free"))

    def test_multi_provider_adapter_delegates_without_leaking_route_prefix(self):
        primary = FakeAdapter("omniroute")
        groq = FakeAdapter("groq")
        registry = ProviderRegistry()
        registry.register("omniroute", primary, 10)
        registry.register("groq", groq, 20)
        router = MultiProviderRoutingAdapter(registry)
        result = router.execute("groq::openai/gpt-oss-120b", "hello", temperature=0)
        self.assertTrue(result.success)
        self.assertEqual(groq.calls[0][0], "openai/gpt-oss-120b")
        self.assertEqual(result.requested_model, "groq::openai/gpt-oss-120b")
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.metadata["route_provider"], "groq")

    def test_only_credentials_enable_independent_free_routes(self):
        from app.core.provider_runtime import configured_free_routes
        clean = {
            "GROQ_API_KEY": "",
            "CEREBRAS_API_KEY": "",
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "groq,cerebras",
        }
        with patch.dict(os.environ, clean, clear=False):
            self.assertEqual(tuple(route.id for route in configured_free_routes()), ("Conding-free", "openrouter/openrouter/free"))
        with patch.dict(os.environ, {**clean, "GROQ_API_KEY": "secret"}, clear=False):
            ids = tuple(route.id for route in configured_free_routes())
            self.assertEqual(ids[0], "Conding-free")
            self.assertEqual(ids[1], "openrouter/openrouter/free")
            self.assertEqual(ids[2:4], (
                "groq::qwen/qwen3.8-27b",
                "groq::qwen/qwen3.6-27b",
            ))
            self.assertIn("groq::openai/gpt-oss-120b", ids)
            self.assertFalse(any(route.startswith("cerebras::") for route in ids))

    def test_omniroute_catalog_adds_only_explicit_free_model_fallbacks(self):
        class LiveOmniRoute:
            def list_models(self):
                ids = ["openrouter/openrouter/free", "auto/coding:free", "openrouter/openai/gpt-oss-20b:free", "cohere/north-mini-code:free", "nvidia/nemotron-3-super-120b:free", "openai/gpt-5"]
                return [RoutingModelInfo(model, "omniroute", [ModelCapability.CODIGO], True) for model in ids]
        from app.core.provider_runtime import configured_mission_routes
        registry = ProviderRegistry()
        registry.register("omniroute", LiveOmniRoute(), 10)
        # Catalog ordering assumes no previously qualified/cooling-down routes.
        # Use fresh stores even when another test or release gate persisted state.
        with tempfile.TemporaryDirectory() as directory:
            clean = {
                "OLYMPUS_FREE_FALLBACK_PROVIDERS": "",
                "OLYMPUS_CAPACITY_STATE_PATH": str(Path(directory) / "capacity.json"),
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory) / "providers.json"),
            }
            with patch.dict(os.environ, clean, clear=True):
                ids = tuple(route.id for route in configured_mission_routes(registry))
        self.assertEqual(ids[0], "Conding-free")
        self.assertEqual(set(ids[1:]), {"openrouter/openrouter/free", "openrouter/openai/gpt-oss-20b:free", "cohere/north-mini-code:free", "nvidia/nemotron-3-super-120b:free"})
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("openai/gpt-5", ids)
        self.assertNotIn("auto/coding:free", ids)

    def test_generic_router_remains_when_catalog_has_no_concrete_free_model(self):
        class MetaOnlyOmniRoute:
            def list_models(self):
                return [
                    RoutingModelInfo("openrouter/openrouter/free", "openrouter", [ModelCapability.CODIGO], True),
                    RoutingModelInfo("auto/coding:free", "auto", [ModelCapability.CODIGO], True),
                    RoutingModelInfo("openai/gpt-5", "openai", [ModelCapability.CODIGO], True),
                ]

        from app.core.provider_runtime import configured_mission_routes
        registry = ProviderRegistry()
        registry.register("omniroute", MetaOnlyOmniRoute(), 10)
        with patch.dict(os.environ, {
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "",
        }, clear=True):
            ids = tuple(route.id for route in configured_mission_routes(registry))

        self.assertEqual(ids, ("Conding-free", "openrouter/openrouter/free"))

    def test_live_catalog_replaces_stale_hard_coded_groq_models(self):
        class LiveGroq:
            def list_models(self):
                return [
                    RoutingModelInfo("openai/gpt-oss-20b", "groq", [ModelCapability.CODIGO], True),
                    RoutingModelInfo("qwen/qwen3.8-27b", "groq", [ModelCapability.CODIGO], True),
                    RoutingModelInfo("allam-2-7b", "groq", [ModelCapability.CODIGO], True),
                    RoutingModelInfo("whisper-large-v3", "groq", [ModelCapability.TEXTO], True),
                ]

        from app.core.provider_runtime import configured_free_routes
        registry = ProviderRegistry()
        registry.register("groq", LiveGroq(), 10)
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "secret",
            "OLYMPUS_FREE_FALLBACK_PROVIDERS": "groq",
        }, clear=True):
            ids = tuple(route.id for route in configured_free_routes(registry))
        self.assertIn("groq::qwen/qwen3.8-27b", ids)
        self.assertIn("groq::openai/gpt-oss-20b", ids)
        self.assertNotIn("groq::llama-3.3-70b-versatile", ids)
        self.assertFalse(any("whisper" in route for route in ids))
        self.assertFalse(any("allam" in route for route in ids))

    def test_explicit_automatic_preference_adds_another_configured_provider(self):
        class LiveGemini:
            def list_models(self):
                return [RoutingModelInfo(
                    "gemini-2.5-flash", "gemini", [ModelCapability.CODIGO], True,
                )]

        from app.core.provider_runtime import configured_free_routes, update_provider_preference
        with tempfile.TemporaryDirectory() as directory:
            registry = ProviderRegistry()
            registry.register("gemini", LiveGemini(), 10)
            with patch.dict(os.environ, {
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
                "GEMINI_API_KEY": "secret",
                "OLYMPUS_FREE_FALLBACK_PROVIDERS": "groq,openrouter",
            }, clear=True):
                update_provider_preference("gemini", enabled=True, automatic=True, priority=25)
                ids = tuple(route.id for route in configured_free_routes(registry))
        self.assertEqual(ids, (
            "Conding-free",
            "openrouter/openrouter/free",
            "gemini::gemini-2.5-flash",
        ))

    def test_saved_priority_controls_the_real_first_model_attempt(self):
        from app.core.provider_runtime import configured_free_routes, update_provider_preference
        from olympus.agent.model_selector import OlympusModelSelector

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
                "GROQ_API_KEY": "secret",
                "OLYMPUS_GROQ_MODELS": "openai/gpt-oss-20b",
                "OLYMPUS_FREE_FALLBACK_PROVIDERS": "groq",
            }, clear=True):
                update_provider_preference("omniroute", enabled=True, automatic=True, priority=10)
                update_provider_preference("groq", enabled=True, automatic=True, priority=5)
                candidates = OlympusModelSelector(configured_free_routes()).select_candidates(
                    "Crie uma landing page funcional"
                )

        self.assertEqual(candidates[0], "groq::openai/gpt-oss-20b")
        self.assertEqual(candidates[1], "Conding-free")
        self.assertEqual(candidates[2], "openrouter/openrouter/free")

    def test_disabling_omniroute_automatic_removes_it_from_mission_routes(self):
        from app.core.provider_runtime import configured_free_routes, update_provider_preference

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "OLYMPUS_PROVIDER_SETTINGS_PATH": str(Path(directory, "settings.json")),
                "GROQ_API_KEY": "secret",
                "OLYMPUS_GROQ_MODELS": "openai/gpt-oss-20b",
                "OLYMPUS_FREE_FALLBACK_PROVIDERS": "groq",
            }, clear=True):
                update_provider_preference("omniroute", enabled=True, automatic=False, priority=10)
                ids = tuple(route.id for route in configured_free_routes())

        self.assertEqual(ids, ("groq::openai/gpt-oss-20b",))

    def test_daily_quota_moves_to_an_independent_provider_and_preserves_progress(self):
        events = []
        plane = AgentControlPlane(
            ".", object(), ProviderSelector(), lambda router, model: model,
            lambda root, model: ProviderLoop(model), events.append,
        )
        result = plane.run_attempts("task")
        self.assertEqual(result.models_attempted, (
            "openrouter/openrouter/free", "groq::openai/gpt-oss-120b"
        ))
        # This fixture models the first independent provider as successful.
        self.assertEqual(result.final.state.status, AgentStatus.COMPLETED)
        event = next(item for item in events if item["event"] == "model_failover")
        self.assertTrue(event["cross_provider"])

    def test_new_model_gets_a_fresh_iteration_budget_and_keeps_files(self):
        state = AgentState(
            "task",
            status=AgentStatus.BLOCKED,
            iteration=24,
            max_iterations=24,
            selected_model="groq::first",
            files_modified=("app/index.html",),
            errors=("malformed action",),
            metadata={"failure_kind": "technical"},
        )
        resumed = state.resume_for_model("groq::second")
        self.assertEqual(resumed.iteration, 0)
        self.assertEqual(resumed.max_iterations, 24)
        self.assertEqual(resumed.files_modified, ("app/index.html",))
        self.assertEqual(resumed.status, AgentStatus.CREATED)

    def test_default_fallback_excludes_provider_without_free_inference_quota(self):
        from app.core.provider_runtime import configured_free_routes
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "groq-secret",
            "CEREBRAS_API_KEY": "cerebras-secret",
        }, clear=True):
            ids = tuple(route.id for route in configured_free_routes())
        self.assertIn("groq::qwen/qwen3-32b", ids)
        self.assertFalse(any(route.startswith("cerebras::") for route in ids))

    def test_bad_provider_credentials_skip_its_other_models(self):
        events = []
        plane = AgentControlPlane(
            ".", object(), ProviderSelector(), lambda router, model: model,
            lambda root, model: GroqQuotaLoop(model), events.append,
        )
        result = plane.run_attempts("task")
        self.assertEqual(result.models_attempted, (
            "openrouter/openrouter/free",
            "groq::openai/gpt-oss-120b",
            "cerebras::qwen-3.8-27b",
        ))
        self.assertEqual(result.final.state.status, AgentStatus.COMPLETED)

    def test_protocol_mismatch_continues_to_next_model_on_same_provider(self):
        class GroqModels:
            def select_candidates(self, task):
                return (
                    "groq::openai/gpt-oss-120b",
                    "groq::llama-3.3-70b-versatile",
                )

        class ToolMismatchLoop(ProviderLoop):
            def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
                state = initial_state or AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
                if selected_model == "groq::openai/gpt-oss-120b":
                    state = state.next_iteration().transition(
                        AgentStatus.BLOCKED,
                        errors=("malformed_response: tool_use_failed",),
                        metadata={"failure_kind": "technical"},
                    )
                else:
                    state = state.resume_for_model(selected_model).transition(AgentStatus.COMPLETED)
                return AgentLoopResult(state, ())

        plane = AgentControlPlane(
            ".", object(), GroqModels(), lambda router, model: model,
            lambda root, model: ToolMismatchLoop(model),
        )
        result = plane.run_attempts("task")
        self.assertEqual(result.models_attempted, (
            "groq::openai/gpt-oss-120b",
            "groq::llama-3.3-70b-versatile",
        ))
        self.assertEqual(result.final.state.status, AgentStatus.COMPLETED)

    def test_single_openrouter_daily_quota_is_not_retried_as_three_fake_routes(self):
        class OnlyOpenRouter:
            def select_candidates(self, task):
                return ("openrouter/openrouter/free",)
        events = []
        plane = AgentControlPlane(
            ".", object(), OnlyOpenRouter(), lambda router, model: model,
            lambda root, model: ProviderLoop(model), events.append,
        )
        result = plane.run_attempts("task")
        self.assertEqual(result.models_attempted, ("openrouter/openrouter/free",))
        self.assertEqual(result.final.state.status, AgentStatus.BLOCKED)
        self.assertIsNone(events[-1]["next_model"])

    def test_secret_configuration_updates_only_requested_keys_atomically(self):
        from scripts.configure_ai_providers import update_env
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, ".env")
            path.write_text("OTHER=value\nGROQ_API_KEY=old\n", encoding="utf-8")
            update_env(path, {"GROQ_API_KEY": "new", "CEREBRAS_API_KEY": "second"})
            content = path.read_text(encoding="utf-8")
            self.assertIn("OTHER=value", content)
            self.assertIn("GROQ_API_KEY=new", content)
            self.assertIn("CEREBRAS_API_KEY=second", content)
            self.assertNotIn("GROQ_API_KEY=old", content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_autonomous_mission_completes_end_to_end_after_cross_provider_failover(self):
        openrouter_failure = RoutingExecutionResult(
            "openrouter/openrouter/free", "", "openrouter", "", 1, 0.0, False,
            "[429] Rate limit exceeded: free-models-per-day", {"http_status": 429}, "rate_limited",
        )
        primary = FakeAdapter("omniroute", openrouter_failure)
        groq = ScriptedAdapter("groq", (
            '{"type":"create_file","target":"olympus/value.py","payload":"def sum_values(a, b):\\n    return a + b\\n","reason":"implement"}',
            '{"type":"create_file","target":"tests/test_value.py","payload":"import unittest\\nfrom olympus.value import sum_values\\nclass TestValue(unittest.TestCase):\\n    def test_sum(self): self.assertEqual(sum_values(2, 3), 5)\\n","reason":"test"}',
            '{"type":"run_test","target":"tests.test_value","payload":["tests.test_value"],"reason":"verify"}',
            '{"type":"finish","target":null,"payload":null,"reason":"verified"}',
        ))
        registry = ProviderRegistry()
        registry.register("omniroute", primary, 10)
        registry.register("groq", groq, 20)
        router = MultiProviderRoutingAdapter(registry)

        class TwoProviders:
            def select_candidates(self, task):
                return ("openrouter/openrouter/free", "groq::openai/gpt-oss-120b")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "olympus").mkdir()
            (root / "olympus" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            report = AutonomousDeveloper(str(root), router, selector=TwoProviders()).run(
                "Implemente uma função Python sum_values com teste unittest.",
                max_iterations=8,
                resume=False,
            )
            self.assertTrue(report.success, report.error)
            self.assertEqual(report.models_attempted, (
                "openrouter/openrouter/free", "groq::openai/gpt-oss-120b"
            ))
            self.assertEqual((root / "olympus" / "value.py").read_text(encoding="utf-8"), "def sum_values(a, b):\n    return a + b\n")

    def test_autonomous_mission_survives_incomplete_instruction_and_finishes(self):
        groq = ScriptedAdapter("groq", (
            '{"type":"create_file","target":null,"payload":"incomplete"}',
            '{"type":"create_file","target":null,"payload":"still incomplete"}',
            '{"type":"create_file","target":"olympus/value.py","payload":"def sum_values(a, b):\\n    return a + b\\n","reason":"implement"}',
            '{"type":"create_file","target":"tests/test_value.py","payload":"import unittest\\nfrom olympus.value import sum_values\\nclass TestValue(unittest.TestCase):\\n    def test_sum(self): self.assertEqual(sum_values(2, 3), 5)\\n","reason":"test"}',
            '{"type":"run_test","target":"tests.test_value","payload":["tests.test_value"],"reason":"verify"}',
            '{"type":"finish","target":null,"payload":null,"reason":"verified"}',
        ))
        registry = ProviderRegistry()
        registry.register("groq", groq, 10)
        router = MultiProviderRoutingAdapter(registry, default_provider="groq")

        class TwoGroqModels:
            def select_candidates(self, task):
                return (
                    "groq::qwen/qwen3-32b",
                    "groq::openai/gpt-oss-20b",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "olympus").mkdir()
            (root / "olympus" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            report = AutonomousDeveloper(str(root), router, selector=TwoGroqModels()).run(
                "Implemente uma função Python sum_values com teste unittest.",
                max_iterations=8,
                resume=False,
            )
            self.assertTrue(report.success, report.error)
            self.assertEqual(report.models_attempted, (
                "groq::qwen/qwen3-32b",
                "groq::openai/gpt-oss-20b",
            ))
            self.assertEqual(
                (root / "olympus" / "value.py").read_text(encoding="utf-8"),
                "def sum_values(a, b):\n    return a + b\n",
            )


if __name__ == "__main__":
    unittest.main()
