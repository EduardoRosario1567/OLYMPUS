# OLYMPUS — Permanent Operating Rules for Coding Agents

## Architecture Boundaries

- **OLYMPUS Core** = decision/intelligence layer (`olympus/classifier.py`, `olympus/registry.py`, `olympus/decision_engine.py`, `olympus/pipeline.py`, `olympus/intelligence_loop.py`, `olympus/judge/`, `olympus/models.py`)
- **HUB** = product/UX layer (`backend/`, `frontend/` — not in this repo's core scope)
- **Routing implementations are replaceable** — Core must not depend on OmniRoute/provider/model
- **Preserve separation**: DecisionRecord = "what Olympus decided" | ExecutionResult = "what actually happened" | QualityEvaluation = "how the result was evaluated"

## Repository Hygiene

- Preserve existing working tree — no unrelated refactors
- No destructive git operations
- No commit/push unless explicitly requested
- No secrets exposure
- No dependency installation unless explicitly authorized
- No migrations unless explicitly authorized

## Patch Execution Rules

- No confirmation inside authorized patch scope
- Diagnose → repair → retest automatically, max 3 cycles
- Stop on BLOCK condition
- Report facts, not assumptions

## Autonomy Levels

| Level | Capability |
|-------|------------|
| L0 | Read-only |
| L1 | Read + create/edit authorized scope + targeted tests + git diff/status + auto-repair |
| L2 | Module-level work only when explicitly granted |
| L3 | Feature-level work only when explicitly granted |

**Never infer higher autonomy.**

## BLOCK Conditions

Immediately halt and report if any of these occur:
- Scope expansion beyond authorization
- New dependency required
- Migration required
- Secret required
- Destructive operation
- Data-loss risk
- Architecture decision not specified
- Repair cycles exhausted (3)

## Test Policy

- **Patch**: Targeted tests only
- **Milestone**: Full regression
- Do not run full suite for every small patch unless explicitly required

## Report Format

```
PATCH <id>: PASS|BLOCKED

CHANGED:
<files>

ACCEPTANCE:
<checks>

TESTS:
<executed/pass/fail/skipped>

CONTEXT:
<manifest + escalations>

VIOLATIONS:
NONE|...

BLOCKED:
NO|reason
```