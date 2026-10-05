from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class SkillSpec:
    id: str
    name: str
    version: str
    description: str
    triggers: Tuple[str, ...]
    allowed_actions: Tuple[str, ...]
    constraints: Tuple[str, ...] = ()
    depends_on: Tuple[str, ...] = ()
    source: str = "builtin"
    guidance: Tuple[str, ...] = ()
    completion_checks: Tuple[str, ...] = ()
    category: str = "core"
    status: str = "active"
    source_url: str = ""
    license: str = ""
    checksum: str = ""

    def matches(self, text: str) -> int:
        if self.status != "active":
            return 0
        haystack = (text or "").lower()
        return sum(1 for token in self.triggers if token.lower() in haystack)
