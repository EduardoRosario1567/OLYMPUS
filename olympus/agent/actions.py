from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Optional


class ActionType(str, Enum):
    READ_FILE = "read_file"
    SEARCH_CODE = "search_code"
    RESEARCH_SOURCES = "research_sources"
    CREATE_FILE = "create_file"
    PATCH_FILE = "patch_file"
    RUN_TEST = "run_test"
    INSPECT_RESULT = "inspect_result"
    FINISH = "finish"


@dataclass(frozen=True)
class AgentAction:
    type: ActionType
    target: Optional[str] = None
    payload: Any = None
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.type not in (ActionType.INSPECT_RESULT, ActionType.FINISH) and not self.target:
            raise ValueError("target is required for this action")

    @property
    def idempotency_key(self) -> str:
        """Stable identity for an action across providers and process resumes.

        Provider supplied identifiers are deliberately ignored: two models that
        propose the same canonical mutation must resolve to the same key.
        """
        canonical = json.dumps(
            {
                "type": self.type.value,
                "target": self.target,
                "payload": self.payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


IDEMPOTENT_GUARDED_ACTIONS = frozenset({
    ActionType.CREATE_FILE,
    ActionType.PATCH_FILE,
})
