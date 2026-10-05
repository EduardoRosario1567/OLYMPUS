import tempfile
import unittest

from olympus.agent.actions import AgentAction, ActionType
from olympus.agent.loop import AgentLoop
from olympus.agent.state import AgentState
from olympus.skills.fabric import SkillsFabric


TASK = 'Faça uma nova versão utilizando as skills Frabic'


class MissingPlanner:
    def next_action(self, *args):
        return AgentAction(ActionType.READ_FILE, target='src/main.py', reason='inspect')


class TestTeste4Regression(unittest.TestCase):
    def test_explicit_fabric_request_activates_skills(self):
        for task in (TASK, TASK.replace('Frabic', 'Fabric'), 'Faça nova versão usando Superpowers'):
            with self.subTest(task=task):
                self.assertEqual(SkillsFabric.choose(task, {}), ('writing-plans',))
        self.assertEqual(SkillsFabric.choose('Escreva uma mensagem de aniversário', {}), ())

    def test_current_budget_error_follows_carried_budget_and_missing_file(self):
        with tempfile.TemporaryDirectory() as root:
            initial = AgentState(task=TASK, errors=('iteration budget exhausted',))
            result = AgentLoop(root, MissingPlanner()).run(TASK, selected_model='qa/last',
                                                         max_iterations=2, initial_state=initial)
        self.assertEqual(result.failure_kind, 'budget')
        self.assertEqual(result.state.status.value, 'blocked')
        self.assertTrue(any('No such file or directory' in error for error in result.state.errors))
        self.assertEqual(result.state.errors[-1], 'iteration budget exhausted')


if __name__ == '__main__': unittest.main()
