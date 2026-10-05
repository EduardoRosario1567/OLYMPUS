# OLYMPUS NEXT — Consolidated Autonomous Agent Runtime

## Runtime contract

OLYMPUS NEXT has one recovery ownership model:

- `AgentLoop` owns one bounded attempt with one selected model: PLAN -> ACT -> OBSERVE -> VERIFY.
- `AgentControlPlane` owns candidate ordering and technical model failover.
- `AutonomousPatchRunner` owns mission-step sequencing and mission termination.
- `DecisionEngine` ranks eligible models; it does not execute them.

## Terminal states

- `COMPLETED`: objective verified.
- `FAILED`: logical/semantic failure; switching providers is not expected to fix it.
- `BLOCKED`: attempt cannot continue safely (technical, policy, or budget). The control plane may fail over only when `failure_kind=technical`.
- `RETRYING`: internal non-terminal action/verification retry inside the current model attempt.

## High-level missions

Explicit STEP sections are optional. A mission with instructions but no STEP becomes `AUTO-1` and is executed iteratively by the existing AgentLoop. The user does not need to pre-decompose the objective.

## Model failures

Technical failures (timeout, rate limit, provider unavailable, connection errors) stop the current AgentLoop attempt as `BLOCKED/technical`. `AgentControlPlane` then tries the next eligible candidate. Logical failures do not trigger provider hopping.

## Deterministic-first policy

Repo mapping, context selection, filesystem operations, patch application, test execution, verification, budgets and state transitions remain local/deterministic. Models are used for semantic planning and code generation only where needed.

## Current Work validation

- Full local suite: 412 tests discovered.
- 412 PASS with 4 environment-gated real OmniRoute tests skipped in Work.
- 0 FAIL, 0 ERROR, 0 ResourceWarning.
- Real OmniRoute gates must be executed once on the Mac where `127.0.0.1:20128` is available.
