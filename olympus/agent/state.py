from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional, Tuple


class AgentStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


TERMINAL_STATUSES = {AgentStatus.COMPLETED, AgentStatus.BLOCKED, AgentStatus.FAILED}


@dataclass(frozen=True)
class AgentState:
    task: str
    task_type: str = "codigo"
    status: AgentStatus = AgentStatus.CREATED
    iteration: int = 0
    max_iterations: int = 12
    selected_model: Optional[str] = None
    current_action: Optional[Any] = None
    files_read: Tuple[str, ...] = ()
    files_modified: Tuple[str, ...] = ()
    tests_run: Tuple[str, ...] = ()
    observations: Tuple[Any, ...] = ()
    errors: Tuple[str, ...] = ()
    quality_score: Optional[float] = None
    final_confidence: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if self.iteration < 0:
            raise ValueError("iteration must be >= 0")
        if self.iteration > self.max_iterations:
            raise ValueError("iteration exceeds max_iterations")
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def transition(self, status: AgentStatus, **changes: Any) -> "AgentState":
        if self.terminal and status != self.status:
            raise ValueError("terminal state cannot transition")
        return replace(self, status=status, **changes)

    def next_iteration(self) -> "AgentState":
        if self.iteration >= self.max_iterations:
            return self.transition(AgentStatus.BLOCKED, errors=self.errors + ("iteration budget exhausted",))
        return replace(self, iteration=self.iteration + 1)

    def resume_for_model(self, selected_model: str) -> "AgentState":
        """Resume a technically interrupted attempt without losing mission progress."""
        metadata = {k: v for k, v in self.metadata.items() if k != "failure_kind"}
        handoffs = list(metadata.get("model_handoffs") or ())
        if self.selected_model and self.selected_model != selected_model:
            handoffs.append({
                "from_model": self.selected_model,
                "to_model": selected_model,
                "last_error": str(self.errors[-1])[:600] if self.errors else None,
                "files_modified": list(self.files_modified),
                "tests_run": list(self.tests_run),
            })
        metadata["model_handoffs"] = handoffs[-5:]
        return replace(
            self,
            status=AgentStatus.CREATED,
            iteration=0,
            selected_model=selected_model,
            current_action=None,
            metadata=metadata,
        )
