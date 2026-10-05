import json
import tempfile
import unittest
from pathlib import Path

from olympus.agent.mission import AutonomousPatchRunner, MissionSpec, MissionStep
from olympus.agent.mission_compiler import MissionCompiler
from olympus.agent.state import AgentStatus
from olympus.routing.interfaces import RoutingExecutionResult
from olympus.skills import SkillRegistry, SkillResolver


TASK = "Crie um arquivo chamado olympus_e2e_test.txt contendo apenas: OLYMPUS_E2E_OK"


class OneModelSelector:
    def select_candidates(self, task):
        return ("model/a",)


class TwoModelSelector:
    def select_candidates(self, task):
        return ("model/a", "model/b")


class ScriptedRouter:
    """Real ModelPlanner/AgentLoop, deterministic provider responses."""
    def __init__(self, scripts):
        self.scripts = {key: list(value) for key, value in scripts.items()}
        self.calls = []

    def execute(self, model_id, prompt, **kwargs):
        self.calls.append((model_id, prompt, kwargs))
        item = self.scripts[model_id].pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict) and item.get("__error__"):
            return RoutingExecutionResult(
                requested_model=model_id, actual_model=model_id, provider="fake",
                output="", latency_ms=1, cost=0.0, success=False,
                error=item["__error__"], status="error",
            )
        output = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return RoutingExecutionResult(
            requested_model=model_id, actual_model=model_id, provider="fake",
            output=output, latency_ms=1, cost=0.0, success=True,
        )


def action(type_, target=None, payload=None, reason="test"):
    data = {"type": type_, "target": target, "payload": payload, "reason": reason}
    return data


class DeterministicMissionContractV280Tests(unittest.TestCase):
    def test_human_prompt_is_compiled_before_skill_selection(self):
        compiled = MissionCompiler().compile(TASK)
        self.assertEqual(compiled.task_family, "file_operation")
        self.assertEqual(compiled.deliverable, "exact_text_file")
        self.assertEqual(compiled.exact_text_artifact, ("olympus_e2e_test.txt", "OLYMPUS_E2E_OK"))
        self.assertIn("file-operations", compiled.required_skills)
        self.assertIn("frontend", compiled.excluded_skills)

        skills = SkillResolver(SkillRegistry()).resolve(
            TASK,
            required=compiled.required_skills,
            supporting=compiled.supporting_skills,
            excluded=compiled.excluded_skills,
            max_inferred=0,
        )
        ids = {skill.id for skill in skills}
        self.assertEqual(ids, {"file-operations"})

    def test_real_runner_rejects_finish_on_typo_then_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ScriptedRouter({"model/a": [
                action("create_file", "olympus_e2e_test.txt", "OLYMPIUS_E2E_OK"),
                action("finish", None, "done"),
                action("create_file", "olympus_e2e_test.txt", "OLYMPUS_E2E_OK"),
                action("finish", None, "done"),
            ]})
            events = []
            runner = AutonomousPatchRunner(tmp, router, selector=OneModelSelector(), telemetry=events.append)
            mission = MissionSpec("E2E", "E2E", (MissionStep("1", "exact", TASK, 6),))
            result = runner.run(mission, resume=False)
            self.assertTrue(result.success)
            self.assertEqual(result.steps[0].loop_result.state.status, AgentStatus.COMPLETED)
            self.assertEqual(Path(tmp, "olympus_e2e_test.txt").read_text().strip(), "OLYMPUS_E2E_OK")
            summary_prompts = [prompt for _, prompt, _ in router.calls]
            self.assertTrue(any("acceptance:" in prompt and "OLYMPIUS_E2E_OK" in prompt for prompt in summary_prompts))

    def test_correct_artifact_survives_timeout_after_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ScriptedRouter({"model/a": [
                action("create_file", "olympus_e2e_test.txt", "OLYMPUS_E2E_OK"),
                {"__error__": "Timeout: the model did not respond within 45 seconds"},
            ]})
            runner = AutonomousPatchRunner(tmp, router, selector=OneModelSelector())
            mission = MissionSpec("E2E", "E2E", (MissionStep("1", "exact", TASK, 4),))
            result = runner.run(mission, resume=False)
            self.assertTrue(result.success)
            state = result.steps[0].loop_result.state
            self.assertEqual(state.status, AgentStatus.COMPLETED)
            self.assertEqual(state.metadata.get("completion_reason"), "acceptance_verified_after_provider_error")
            self.assertIn("Timeout", state.metadata.get("previous_attempt_error", ""))

    def test_timeout_at_budget_boundary_still_fails_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            # model/a consumes all 8 iterations and fails technically on the 8th;
            # model/b must still receive a bounded recovery attempt.
            a = [action("inspect_result", None, "checking") for _ in range(7)]
            a.append({"__error__": "Timeout: the model did not respond within 45 seconds"})
            b = [
                action("create_file", "olympus_e2e_test.txt", "OLYMPUS_E2E_OK"),
                action("finish", None, "done"),
            ]
            router = ScriptedRouter({"model/a": a, "model/b": b})
            events = []
            runner = AutonomousPatchRunner(tmp, router, selector=TwoModelSelector(), telemetry=events.append)
            mission = MissionSpec("E2E", "E2E", (MissionStep("1", "exact", TASK, 8),))
            result = runner.run(mission, resume=False)
            self.assertTrue(result.success)
            self.assertEqual(result.steps[0].models_attempted, ("model/a", "model/b"))
            self.assertTrue(any(e.get("event") == "model_failover" and e.get("next_model") == "model/b" for e in events))

    def test_exact_parser_does_not_swallow_followup_instruction(self):
        compiled = MissionCompiler().compile(
            "Crie um arquivo chamado a.txt contendo apenas: OK. Depois rode os testes."
        )
        self.assertEqual(compiled.exact_text_artifact, ("a.txt", "OK"))


if __name__ == "__main__":
    unittest.main()

class SkillFamilyMatrixV280Tests(unittest.TestCase):
    def test_family_matrix_routes_to_required_skill_graph(self):
        cases = [
            ("Crie uma landing page responsiva", "web", "frontend"),
            ("Crie um jogo simples de memória", "game", "game-development"),
            ("Crie um aplicativo para cadastro", "application", "app-architecture"),
            ("Calcule juros compostos de 1000 a 2%", "mathematics", "mathematics"),
            ("Analise esta planilha de dados", "data_analysis", "data-analysis"),
            ("Pesquise fontes sobre energia solar", "research", "research"),
            ("Escreva um resumo executivo", "writing", "writing"),
        ]
        compiler = MissionCompiler()
        for prompt, family, skill in cases:
            with self.subTest(prompt=prompt):
                compiled = compiler.compile(prompt)
                self.assertEqual(compiled.task_family, family)
                self.assertIn(skill, compiled.required_skills)

    def test_file_operation_does_not_activate_product_ui_skills(self):
        compiled = MissionCompiler().compile(TASK)
        resolved = SkillResolver(SkillRegistry()).resolve(
            TASK,
            required=compiled.required_skills,
            supporting=compiled.supporting_skills,
            excluded=compiled.excluded_skills,
            max_inferred=0,
        )
        ids = {skill.id for skill in resolved}
        self.assertFalse(ids & {"frontend", "product-experience", "visual-design", "accessibility"})
