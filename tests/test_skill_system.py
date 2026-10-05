import tempfile
import unittest
from pathlib import Path
from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.skills import SkillExecutor, SkillPolicy, SkillPolicyError, SkillRegistry, SkillResolver

class Delegate:
    def __init__(self): self.called=False
    def execute(self, action): self.called=True; return "ok"

class TestSkillSystem(unittest.TestCase):
    def test_registry_and_resolution(self):
        reg=SkillRegistry(); ids=reg.ids()
        self.assertIn("coding", ids); self.assertIn("frontend", ids)
        self.assertIn("testing", [s.id for s in SkillResolver(reg).resolve("Improve React UI tests")])
    def test_dependency(self):
        ids=[s.id for s in SkillResolver(SkillRegistry()).resolve("improve frontend")]
        self.assertLess(ids.index("frontend"), len(ids))
        self.assertIn("testing", ids)
    def test_policy_blocks_unauthorized_action(self):
        with self.assertRaises(SkillPolicyError): SkillPolicy(("read_file",)).check(ActionType.PATCH_FILE)
    def test_executor_blocks_before_delegate(self):
        d=Delegate(); e=SkillExecutor(d,("read_file",))
        with self.assertRaises(SkillPolicyError): e.execute(AgentAction(ActionType.PATCH_FILE,"x.py",{"new_content":"x"}))
        self.assertFalse(d.called)
    def test_loop_skill_policy_blocks(self):
        class P:
            def next_action(self,*args,**kwargs): return AgentAction(ActionType.PATCH_FILE,"x.py",{"new_content":"x"})
        with tempfile.TemporaryDirectory() as td:
            r=AgentLoop(td,P(),skill_policy=SkillPolicy(("read_file",))).run("security review",max_iterations=1)
            self.assertEqual(r.state.status.value,"blocked")
            self.assertEqual(r.failure_kind,"policy")

if __name__ == '__main__': unittest.main()
