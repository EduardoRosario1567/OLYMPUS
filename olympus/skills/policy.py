class SkillPolicyError(PermissionError): pass
class SkillPolicy:
    def __init__(self, allowed_actions): self.allowed_actions={getattr(a,'value',a) for a in allowed_actions}
    def check(self, action_type):
        action=getattr(action_type,'value',action_type)
        if action not in self.allowed_actions: raise SkillPolicyError(f"skill policy denies action: {action}")
