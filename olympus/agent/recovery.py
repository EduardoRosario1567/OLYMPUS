from enum import Enum


class FailureKind(str, Enum):
    TECHNICAL = "technical"
    LOGICAL = "logical"
    BUDGET = "budget"
    POLICY = "policy"


_TECHNICAL_TOKENS = (
    "timeout",
    "timed out",
    "429",
    "rate limit",
    "rate_limit",
    "provider error",
    "provider_error",
    "authentication_error",
    "billing_error",
    "unavailable",
    "connection",
    "temporarily unavailable",
    "malformed_response",
    "tool_use_failed",
    "model returned no textual action",
    "malformed action",
    "target is required",
    "missing action type",
    "unknown action type",
    "response is not a recoverable web document",
    "max_tokens",
    "invalid_request_error",
)


def classify_failure(error: object) -> FailureKind:
    text = str(error or "").lower()
    if any(token in text for token in _TECHNICAL_TOKENS):
        return FailureKind.TECHNICAL
    return FailureKind.LOGICAL
