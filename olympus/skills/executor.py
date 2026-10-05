from olympus.skills.policy import SkillPolicy
class SkillExecutor:
    def __init__(self, executor, allowed_actions): self.executor=executor; self.policy=SkillPolicy(allowed_actions)
    def execute(self, action): self.policy.check(action.type); return self.executor.execute(action)
