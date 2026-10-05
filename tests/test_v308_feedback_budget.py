import json
import unittest
from olympus.agent.actions import AgentAction,ActionType
from olympus.agent.executor import ActionObservation
from olympus.agent.state import AgentState
from olympus.agent.loop import AgentLoop
from olympus.agent.planner import ModelPlanner

class FeedbackBudgetTests(unittest.TestCase):
    def test_three_large_search_results_and_skill_contract_remain_parseable(self):
        observations=tuple(ActionObservation(True,AgentAction(ActionType.SEARCH_CODE,'.','x'),output=[('src/'+str(i)+'x'*160+'.py',1,'x'*200) for i in range(50)]) for _ in range(3))
        state=AgentState('task',observations=observations,errors=('x'*600,)*3)
        summary=AgentLoop._state_summary(state,{'ids':['coding','testing'],'guidance':['x'*240]*8,'completion_checks':['x'*240]*8})
        bounded=ModelPlanner._bounded_state_summary(summary)
        try: result=json.loads(bounded)
        except ValueError as error: self.fail('Planner receives truncated JSON: '+str(error))
        self.assertLessEqual(len(bounded),6000)
        self.assertIn('professional_skill_contract',result)
        self.assertTrue(result['recent_actions'][0].get('output'))
        self.assertIn('recent_errors',result)

if __name__=='__main__': unittest.main()
