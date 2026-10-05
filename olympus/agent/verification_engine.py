from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Optional, Tuple


class VerificationStatus(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"
    FAILED = "failed"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class VerificationEvidence:
    kind: str
    summary: str
    data: Any = None


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    status: CheckStatus
    evidence: Tuple[VerificationEvidence, ...] = ()
    required: bool = True


@dataclass(frozen=True)
class VerificationPlan:
    checks: Tuple[VerificationCheck, ...] = ()
    minimum_required_checks: int = 1


@dataclass(frozen=True)
class VerificationReport:
    status: VerificationStatus
    checks: Tuple[VerificationCheck, ...]
    evidence: Tuple[VerificationEvidence, ...]
    confidence: float
    errors: Tuple[str, ...] = ()

    @property
    def completed(self) -> bool:
        return self.status == VerificationStatus.FULL

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "checks": [
                {"name": c.name, "status": c.status.value, "required": c.required,
                 "evidence": [{"kind": e.kind, "summary": e.summary, "data": e.data} for e in c.evidence]}
                for c in self.checks
            ],
            "evidence": [{"kind": e.kind, "summary": e.summary, "data": e.data} for e in self.evidence],
            "errors": list(self.errors),
        }


class VerificationEngine:
    """Evidence-first completion authority.

    FINISH is only a request to verify. FULL is the only report status that
    authorizes COMPLETED. Confidence summarizes evidence; it never replaces it.
    """

    def evaluate(self, plan: VerificationPlan) -> VerificationReport:
        checks = tuple(plan.checks)
        evidence = tuple(e for c in checks for e in c.evidence)
        required = tuple(c for c in checks if c.required)
        failed = tuple(c for c in required if c.status == CheckStatus.FAIL)
        passed = tuple(c for c in required if c.status == CheckStatus.PASS)
        errors = tuple("verification failed: %s" % c.name for c in failed)

        if failed:
            status = VerificationStatus.FAILED
        elif len(passed) >= max(1, plan.minimum_required_checks) and len(passed) == len(required):
            status = VerificationStatus.FULL
        elif checks:
            status = VerificationStatus.PARTIAL
        else:
            status = VerificationStatus.NONE

        if not checks:
            confidence = 0.0
        else:
            confidence = sum(1.0 if c.status == CheckStatus.PASS else 0.0 for c in checks) / len(checks)
        return VerificationReport(status, checks, evidence, round(confidence, 4), errors)
