import tempfile
import unittest
from pathlib import Path

from olympus.agent.mission_compiler import MissionCompiler
from olympus.agent.mission import AutonomousPatchRunner, parse_mission
from olympus.agent.loop import AgentLoopResult
from olympus.agent.mission_checkpoint import MissionCheckpointStore
from olympus.agent.state import AgentState, AgentStatus


class _Selector:
    def select_candidates(self, _task):
        return ("model/a",)


class _CaptureLoop:
    def __init__(self, calls): self.calls = calls
    def run(self, task, selected_model=None, max_iterations=12, initial_state=None):
        self.calls.append((task, initial_state))
        state = initial_state or AgentState(task, selected_model=selected_model, max_iterations=max_iterations)
        return AgentLoopResult(state.transition(AgentStatus.COMPLETED), ())


class MissionCompilerV230Tests(unittest.TestCase):
    def test_compiler_preserves_constraints_and_adds_web_acceptance_without_model(self):
        request = (
            "Crie uma landing page profissional para o Olympus. Inclua menu, benefícios e formulário. "
            "Não use Lorem ipsum. Deve funcionar no celular e valide o formulário."
        )
        compiled = MissionCompiler().compile(request)
        self.assertEqual(compiled.deliverable, "static_web")
        self.assertTrue(any("Lorem" in item for item in compiled.constraints))
        self.assertTrue(any("app/index.html" in item for item in compiled.acceptance))
        self.assertIn("OLYMPUS_EXECUTION_CONTRACT", compiled.instruction())

    def test_runner_sends_compiled_contract_and_retains_original_in_checkpoint(self):
        request = (
            "Crie uma landing page profissional para o Olympus com menu, proposta de valor, "
            "três benefícios, comparação, formulário funcional, rodapé, responsividade e acessibilidade. "
            "Não use Lorem ipsum nem dependências externas; teste antes de concluir."
        )
        calls=[]
        with tempfile.TemporaryDirectory() as directory:
            store=MissionCheckpointStore(directory)
            runner=AutonomousPatchRunner(
                directory, object(), selector=_Selector(), planner_factory=lambda _r,_m: object(),
                loop_factory=lambda _root,_planner: _CaptureLoop(calls), checkpoint_store=store,
            )
            result=runner.run(parse_mission(request))
            checkpoint=store.load("MISSION")
        self.assertTrue(result.success)
        self.assertTrue(calls[0][0].startswith("OLYMPUS_EXECUTION_CONTRACT"))
        self.assertEqual(checkpoint.metadata["original_request"], request)
        self.assertIn("compiled_mission", checkpoint.metadata)


if __name__ == "__main__": unittest.main()
