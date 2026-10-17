from dataclasses import dataclass
from enum import Enum
import re

from olympus.agent.actions import ActionType, AgentAction


class AutonomyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_USER = "require_user"
    BLOCK = "block"


@dataclass(frozen=True)
class AutonomyResult:
    decision: AutonomyDecision
    reason: str


class AutonomyPolicy:
    SAFE_ACTIONS = {ActionType.READ_FILE, ActionType.SEARCH_CODE, ActionType.CREATE_FILE, ActionType.PATCH_FILE, ActionType.RUN_TEST, ActionType.INSPECT_RESULT, ActionType.FINISH}
    DANGEROUS_PATTERNS = (
        r"(?<![A-Za-z0-9_])rm\s+",
        r"(?<![A-Za-z0-9_])git\s+(?:reset|clean|push)\b",
        r"(?<![A-Za-z0-9_])(?:pip|npm)\s+install\b",
        r"(?<![A-Za-z0-9_])\.\./",
    )

    def evaluate(self, action: AgentAction) -> AutonomyResult:
        if action.type in (ActionType.RESEARCH_SOURCES, ActionType.IMPORT_ASSET):
            return AutonomyResult(AutonomyDecision.ALLOW, "bounded public source research")
        text = (str(action.target or "") + " " + str(action.payload or "")).lower()
        if any(re.search(pattern, text) for pattern in self.DANGEROUS_PATTERNS):
            return AutonomyResult(AutonomyDecision.BLOCK, "destructive or out-of-policy operation")
        if action.type in self.SAFE_ACTIONS:
            return AutonomyResult(AutonomyDecision.ALLOW, "safe runtime action")
        return AutonomyResult(AutonomyDecision.REQUIRE_USER, "unknown action requires user")
