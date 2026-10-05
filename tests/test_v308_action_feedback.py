import json
import tempfile
import unittest
from pathlib import Path
from olympus.agent.actions import ActionType,AgentAction
from olympus.agent.executor import ActionExecutor,ActionObservation
from olympus.agent.loop import AgentLoop
from olympus.agent.repo_map import build_repo_map
from olympus.agent.state import AgentState,AgentStatus

class FeedbackPlanner:
    def __init__(self): self.summaries=[]
    def next_action(self,task,state_summary,context,available):
        state=json.loads(state_summary);self.summaries.append(state)
        matches=[row for a in state['recent_actions'] if a['action']=='search_code' for row in a.get('output',[])]
        if not state['files_modified']:
            if any(row[0]=='src/main.py' and 'return 1' in row[2] for row in matches):
                return AgentAction(ActionType.PATCH_FILE,'src/main.py',{'operation':'replace_function','symbol':'value','new_content':'def value():\n    return 7'})
            return AgentAction(ActionType.SEARCH_CODE,'.','return 1')
        return AgentAction(ActionType.FINISH)

class ActionFeedbackTests(unittest.TestCase):
    def fixture(self,root):
        (root/'src').mkdir();(root/'src/main.py').write_text('def value():\n    return 1\n')
        (root/'.olympus/checkpoints').mkdir(parents=True)
        (root/'.olympus/checkpoints/DEVELOP.json').write_text('{"task":"return 1","token":"INTERNAL_SENTINEL"}')
        (root/'README.md').write_text('Application repository\n')

    def test_search_result_reaches_planner_and_enables_real_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            planner=FeedbackPlanner()
            result=AgentLoop(tmp,planner).run('Faça uma nova versão utilizando as skills Frabic',max_iterations=4)
            self.assertEqual(result.state.status,AgentStatus.COMPLETED)
            self.assertIn('return 7',(root/'src/main.py').read_text())
            self.assertIn('src/main.py',result.state.files_modified)
            self.assertEqual(len(result.history),3)

    def test_repo_map_and_search_exclude_internal_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            repo=build_repo_map(tmp)
            self.assertEqual(set(repo.files),{'src/main.py','README.md'})
            found=ActionExecutor(tmp).execute(AgentAction(ActionType.SEARCH_CODE,'.','return 1'))
            self.assertTrue(found.success)
            self.assertEqual(found.output,[('src/main.py',2,'return 1')])
            self.assertNotIn('INTERNAL_SENTINEL',json.dumps(found.output))

    def test_project_inventory_visible_without_task_keyword_matches(self):
        class InventoryPlanner:
            def next_action(self,task,state_summary,context,available):
                state=json.loads(state_summary)
                if 'src/main.py' in context.selected_files:
                    return AgentAction(ActionType.CREATE_FILE,'src/generated.py','value = 7\n') if not state['files_modified'] else AgentAction(ActionType.FINISH)
                return AgentAction(ActionType.SEARCH_CODE,'.','nonexistent')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            result=AgentLoop(tmp,InventoryPlanner()).run('Atualize usando Frabic',max_iterations=3)
            self.assertEqual(result.state.status,AgentStatus.COMPLETED)
            self.assertTrue((root/'src/generated.py').exists())

    def test_empty_search_is_explicitly_observable(self):
        observation=ActionObservation(True,AgentAction(ActionType.SEARCH_CODE,'.','missing'),output=[])
        summary=json.loads(AgentLoop._state_summary(AgentState('task',observations=(observation,))))
        recent=summary['recent_actions'][0]
        self.assertIn('output',recent)
        self.assertEqual(recent['output'],[])
        self.assertEqual(recent['query'],'missing')

    def test_feedback_is_bounded_and_valid_json(self):
        result=[('src/file%d.py'%i,1,'x'*20000) for i in range(50)]
        observation=ActionObservation(True,AgentAction(ActionType.SEARCH_CODE,'.','x'),output=result)
        summary=AgentLoop._state_summary(AgentState('task',observations=(observation,)))
        decoded=json.loads(summary)
        self.assertLess(len(summary),7000)
        self.assertIn('output',decoded['recent_actions'][0])
        self.assertEqual(decoded['recent_actions'][0]['output'][0][0],'src/file0.py')
        self.assertTrue(decoded['recent_actions'][0]['output_truncated'])

    def test_read_source_output_is_visible_but_runtime_read_is_not(self):
        source=ActionObservation(True,AgentAction(ActionType.READ_FILE,'src/main.py'),output='def value():\n    return 1\n')
        runtime=ActionObservation(True,AgentAction(ActionType.READ_FILE,'.olympus/checkpoints/DEVELOP.json'),output='INTERNAL_SENTINEL')
        summary=AgentLoop._state_summary(AgentState('task',observations=(source,runtime)))
        data=json.loads(summary)
        self.assertIn('def value()',data['recent_actions'][0].get('output',''))
        self.assertNotIn('INTERNAL_SENTINEL',summary)

if __name__=='__main__': unittest.main()
