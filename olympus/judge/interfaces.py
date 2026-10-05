"""
Judge Engine Interfaces — PATCH 005A

Contratos tipados para avaliação de qualidade.
Zero dependências externas, zero coupling com providers específicos.
Python 3.9 compatible.
"""

from dataclasses import dataclass
from typing import Optional, Protocol
from typing import runtime_checkable


@runtime_checkable
class EvaluationPolicy(Protocol):
    """
    Contract for evaluation policies.

    Represents a policy that defines how to evaluate a task result.
    Implementations are provided by evaluators — not hardcoded here.
    """

    @property
    def task_type(self) -> str:
        """Task type this policy applies to."""
        ...

    @property
    def minimum_quality_score(self) -> float:
        """Minimum quality score required to pass (0.0 to 1.0)."""
        ...

    @property
    def pass_threshold(self) -> float:
        """Threshold for passing — alias for minimum_quality_score for clarity."""
        ...

    @property
    def criteria(self) -> dict:
        """Criteria definitions for this policy (extensible)."""
        ...

    @property
    def metadata(self) -> dict:
        """Arbitrary metadata for the policy."""
        ...


@dataclass(frozen=True)
class SimpleEvaluationPolicy:
    """
    Simple immutable implementation of EvaluationPolicy.

    Use when a concrete policy object is needed without subclassing Protocol.
    """
    task_type: str
    minimum_quality_score: float
    criteria: Optional[dict] = None
    metadata: Optional[dict] = None

    @property
    def pass_threshold(self) -> float:
        return self.minimum_quality_score

    def __post_init__(self) -> None:
        if not (0.0 <= self.minimum_quality_score <= 1.0):
            raise ValueError(
                f"minimum_quality_score must be in [0.0, 1.0], got {self.minimum_quality_score}"
            )
        if self.criteria is None:
            object.__setattr__(self, "criteria", {})
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@dataclass(frozen=True)
class JudgeContext:
    """
    Immutable context for a single evaluation.

    Contains all information needed to evaluate a task execution result.
    No direct dependency on ExecutionResult object — uses simple types.
    """
    # Task identification
    task_id: str
    task_type: str
    task_description: str

    # Decision context
    decision_id: str
    decision_confidence: float

    # Execution context
    execution_result_id: str
    requested_model: str
    actual_model: str
    provider: str

    # Execution result
    output: str
    execution_status: str

    # Extensible metadata
    metadata: Optional[dict] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@dataclass(frozen=True)
class JudgeResult:
    """
    Immutable result of a single evaluation.

    Quality score is ALWAYS in range [0.0, 1.0].
    passed means: quality_score >= policy.pass_threshold
    """
    quality_score: float
    passed: bool
    evaluator: str
    reason: str
    criteria: dict
    metadata: Optional[dict] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.quality_score <= 1.0):
            raise ValueError(
                f"quality_score must be in [0.0, 1.0], got {self.quality_score}"
            )
        if self.criteria is None:
            object.__setattr__(self, "criteria", {})
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@runtime_checkable
class JudgeAdapter(Protocol):
    """
    Protocol for judge evaluators.

    Implementations evaluate a JudgeContext and return a JudgeResult.
    Caller does not depend on concrete implementation.
    """

    def evaluate(self, context: JudgeContext) -> JudgeResult:
        """
        Evaluate the execution result against evaluation criteria.

        Args:
            context: JudgeContext with task, decision, and execution info

        Returns:
            JudgeResult with quality_score in [0.0, 1.0], passed flag,
            evaluator identifier, reason, criteria breakdown, and metadata
        """
        ...


class _FakeJudge:
    """
    Fake implementation of JudgeAdapter for testing.

    Not exported — use FakeJudge in tests module.
    """
    def __init__(self, fixed_result: Optional[JudgeResult] = None):
        self._fixed_result = fixed_result

    def evaluate(self, context: JudgeContext) -> JudgeResult:
        if self._fixed_result is not None:
            return self._fixed_result
        return JudgeResult(
            quality_score=0.8,
            passed=True,
            evaluator="fake",
            reason="fake evaluation",
            criteria={"fake_criterion": 0.8},
            metadata={"context_task_id": context.task_id},
        )

# Re-export for test usage
FakeJudge = _FakeJudge