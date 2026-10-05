"""
Final Confidence Policy — PATCH 005F

Combines decision confidence, quality score, and execution status into a single
deterministic final confidence with actionable recommendation.

Rules:
- technical execution != success:
    confidence=0, action=reselect
- technical success:
    compute deterministic confidence from decision_confidence + quality_score

Default weights (quality has greater weight):
  quality_score=0.70
  decision_confidence=0.30

Thresholds:
  deliver >= 0.80
  review >= 0.60
  reselect < 0.60

No LLM, no network, no persistence, no retry, no model reselect execution.
Python 3.9 compatible.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict
import copy


# Canonical action values
ACTION_DELIVER = "deliver"
ACTION_REVIEW = "review"
ACTION_RESELECT = "reselect"

# Default weights (quality > decision)
DEFAULT_QUALITY_WEIGHT = 0.70
DEFAULT_DECISION_WEIGHT = 0.30

# Default thresholds
DEFAULT_DELIVER_THRESHOLD = 0.80
DEFAULT_REVIEW_THRESHOLD = 0.60

# Canonical execution status for success
_SUCCESS_STATUS = "success"


@dataclass(frozen=True)
class FinalConfidenceConfig:
    """
    Configuration for Final Confidence computation.

    All values are validated on construction.
    Immutable after creation.
    """
    quality_weight: float = DEFAULT_QUALITY_WEIGHT
    decision_weight: float = DEFAULT_DECISION_WEIGHT
    deliver_threshold: float = DEFAULT_DELIVER_THRESHOLD
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD

    def __post_init__(self) -> None:
        # Validate weights
        if not (0.0 <= self.quality_weight <= 1.0):
            raise ValueError(
                f"quality_weight must be in [0.0, 1.0], got {self.quality_weight}"
            )
        if not (0.0 <= self.decision_weight <= 1.0):
            raise ValueError(
                f"decision_weight must be in [0.0, 1.0], got {self.decision_weight}"
            )
        # Weights must sum to 1.0 (within floating point tolerance)
        total_weight = self.quality_weight + self.decision_weight
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError(
                f"weights must sum to 1.0, got {total_weight} "
                f"(quality={self.quality_weight}, decision={self.decision_weight})"
            )

        # Validate thresholds
        if not (0.0 <= self.deliver_threshold <= 1.0):
            raise ValueError(
                f"deliver_threshold must be in [0.0, 1.0], got {self.deliver_threshold}"
            )
        if not (0.0 <= self.review_threshold <= 1.0):
            raise ValueError(
                f"review_threshold must be in [0.0, 1.0], got {self.review_threshold}"
            )
        if self.review_threshold >= self.deliver_threshold:
            raise ValueError(
                f"review_threshold ({self.review_threshold}) must be < "
                f"deliver_threshold ({self.deliver_threshold})"
            )

    @property
    def weights_sum(self) -> float:
        """Sum of weights (always 1.0 due to validation)."""
        return self.quality_weight + self.decision_weight


@dataclass(frozen=True)
class FinalConfidenceResult:
    """
    Immutable result of final confidence computation.

    Attributes:
        confidence: Final confidence score in [0.0, 1.0]
        action: One of "deliver", "review", "reselect"
        reason: Human-readable explanation of the decision
        metadata: Extensible metadata including inputs and configuration
    """
    confidence: float
    action: str
    reason: str
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )
        valid_actions = {ACTION_DELIVER, ACTION_REVIEW, ACTION_RESELECT}
        if self.action not in valid_actions:
            raise ValueError(
                f"action must be one of {valid_actions}, got {self.action}"
            )
        if not isinstance(self.reason, str):
            raise ValueError("reason must be a string")
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


class FinalConfidenceCalculator:
    """
    Deterministic Final Confidence calculator.

    Computes a single confidence score from:
    - decision_confidence: Confidence from the DecisionEngine (0.0-1.0)
    - quality_score: Quality score from JudgeResult (0.0-1.0)
    - execution_status: Technical execution status

    Returns FinalConfidenceResult with actionable recommendation.
    """

    def __init__(self, config: Optional[FinalConfidenceConfig] = None) -> None:
        """
        Initialize with optional custom configuration.

        Args:
            config: FinalConfidenceConfig with custom weights/thresholds.
                    Uses defaults if not provided.
        """
        self._config = config or FinalConfidenceConfig()

    @property
    def config(self) -> FinalConfidenceConfig:
        """Return the current configuration (immutable)."""
        return self._config

    def compute(
        self,
        decision_confidence: float,
        quality_score: float,
        execution_status: str,
    ) -> FinalConfidenceResult:
        """
        Compute final confidence and action recommendation.

        Args:
            decision_confidence: DecisionEngine confidence in [0.0, 1.0]
            quality_score: JudgeResult quality_score in [0.0, 1.0]
            execution_status: Technical execution status string

        Returns:
            FinalConfidenceResult with confidence, action, reason, and metadata

        Raises:
            ValueError: If inputs are out of valid ranges
        """
        # Validate inputs
        self._validate_inputs(decision_confidence, quality_score, execution_status)

        # Rule: technical execution != success -> immediate reselect
        if execution_status != _SUCCESS_STATUS:
            return self._technical_failure_result(
                decision_confidence, quality_score, execution_status
            )

        # Technical success: compute weighted confidence
        confidence = self._compute_weighted_confidence(
            decision_confidence, quality_score
        )

        # Determine action based on thresholds
        action, reason = self._determine_action(confidence)

        # Build metadata
        metadata = {
            "decision_confidence": decision_confidence,
            "quality_score": quality_score,
            "execution_status": execution_status,
            "weights": {
                "quality": self._config.quality_weight,
                "decision": self._config.decision_weight,
            },
            "thresholds": {
                "deliver": self._config.deliver_threshold,
                "review": self._config.review_threshold,
            },
            "computed_confidence": confidence,
        }

        return FinalConfidenceResult(
            confidence=confidence,
            action=action,
            reason=reason,
            metadata=metadata,
        )

    def _validate_inputs(
        self,
        decision_confidence: float,
        quality_score: float,
        execution_status: str,
    ) -> None:
        """Validate input ranges."""
        if not (0.0 <= decision_confidence <= 1.0):
            raise ValueError(
                f"decision_confidence must be in [0.0, 1.0], got {decision_confidence}"
            )
        if not (0.0 <= quality_score <= 1.0):
            raise ValueError(
                f"quality_score must be in [0.0, 1.0], got {quality_score}"
            )
        if not isinstance(execution_status, str):
            raise ValueError("execution_status must be a string")

    def _compute_weighted_confidence(
        self,
        decision_confidence: float,
        quality_score: float,
    ) -> float:
        """
        Compute deterministic weighted confidence.

        Uses: confidence = quality_weight * quality_score + decision_weight * decision_confidence

        This is NOT simple multiplication - it's a weighted sum.
        """
        weighted = (
            self._config.quality_weight * quality_score
            + self._config.decision_weight * decision_confidence
        )
        # Clamp for safety
        return max(0.0, min(1.0, weighted))

    def _determine_action(self, confidence: float) -> tuple[str, str]:
        """
        Determine action based on confidence and thresholds.

        Returns:
            (action, reason) tuple
        """
        if confidence >= self._config.deliver_threshold:
            return (
                ACTION_DELIVER,
                f"Final confidence {confidence:.3f} >= deliver threshold "
                f"{self._config.deliver_threshold:.2f} — deliver result."
            )
        elif confidence >= self._config.review_threshold:
            return (
                ACTION_REVIEW,
                f"Final confidence {confidence:.3f} >= review threshold "
                f"{self._config.review_threshold:.2f} but < deliver threshold "
                f"{self._config.deliver_threshold:.2f} — requires human review."
            )
        else:
            return (
                ACTION_RESELECT,
                f"Final confidence {confidence:.3f} < review threshold "
                f"{self._config.review_threshold:.2f} — reselect model/strategy."
            )

    def _technical_failure_result(
        self,
        decision_confidence: float,
        quality_score: float,
        execution_status: str,
    ) -> FinalConfidenceResult:
        """Return result for technical execution failure (short-circuit)."""
        return FinalConfidenceResult(
            confidence=0.0,
            action=ACTION_RESELECT,
            reason=(
                f"Technical execution did not succeed (status='{execution_status}'); "
                "final confidence is 0.0 and reselect is required."
            ),
            metadata={
                "decision_confidence": decision_confidence,
                "quality_score": quality_score,
                "execution_status": execution_status,
                "weights": {
                    "quality": self._config.quality_weight,
                    "decision": self._config.decision_weight,
                },
                "thresholds": {
                    "deliver": self._config.deliver_threshold,
                    "review": self._config.review_threshold,
                },
                "technical_failure": True,
            },
        )


# Convenience function for direct computation
def compute_final_confidence(
    decision_confidence: float,
    quality_score: float,
    execution_status: str,
    quality_weight: float = DEFAULT_QUALITY_WEIGHT,
    decision_weight: float = DEFAULT_DECISION_WEIGHT,
    deliver_threshold: float = DEFAULT_DELIVER_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> FinalConfidenceResult:
    """
    Convenience function for one-off final confidence computation.

    Args:
        decision_confidence: DecisionEngine confidence in [0.0, 1.0]
        quality_score: JudgeResult quality_score in [0.0, 1.0]
        execution_status: Technical execution status string
        quality_weight: Weight for quality_score (default 0.70)
        decision_weight: Weight for decision_confidence (default 0.30)
        deliver_threshold: Threshold for deliver action (default 0.80)
        review_threshold: Threshold for review action (default 0.60)

    Returns:
        FinalConfidenceResult
    """
    config = FinalConfidenceConfig(
        quality_weight=quality_weight,
        decision_weight=decision_weight,
        deliver_threshold=deliver_threshold,
        review_threshold=review_threshold,
    )
    calculator = FinalConfidenceCalculator(config=config)
    return calculator.compute(decision_confidence, quality_score, execution_status)


__all__ = [
    "FinalConfidenceConfig",
    "FinalConfidenceResult",
    "FinalConfidenceCalculator",
    "compute_final_confidence",
    "ACTION_DELIVER",
    "ACTION_REVIEW",
    "ACTION_RESELECT",
    "DEFAULT_QUALITY_WEIGHT",
    "DEFAULT_DECISION_WEIGHT",
    "DEFAULT_DELIVER_THRESHOLD",
    "DEFAULT_REVIEW_THRESHOLD",
]