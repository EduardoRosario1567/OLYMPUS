# OLYMPUS — Source of Truth

## Product intent

OLYMPUS is not a single coding model. It is the control/runtime layer that selects models, constrains context and permissions, executes structured actions, verifies results, records telemetry, and stops safely.

## Canonical responsibility boundaries

### DecisionEngine / OlympusModelSelector
Owns task classification and ordered model eligibility. It does **not** execute models.

### AutonomousPatchRunner
Owns a mission and **model failover between attempts**. A technical failure of one model does not mean the mission failed. It may try the next eligible candidate. Logical/policy/budget failures stop the mission.

### AgentLoop
Owns exactly one bounded model attempt:

`PLAN -> ACT -> OBSERVE -> VERIFY -> NEXT/FINISH`

It owns iteration budget and action/verification retry. A planner/router technical failure ends the current model attempt as `BLOCKED` with `failure_kind=technical`, allowing the mission layer to fail over. A semantic planner failure is `FAILED`.

### ModelPlanner
Owns one next-action inference. It never executes filesystem/shell operations.

### ContextEngine / RepoMap
Own deterministic repository discovery and bounded context. Whole-repository prompt injection is forbidden.

### ActionExecutor
Owns deterministic execution of structured actions under `AutonomyPolicy`.

### PatchEngine
Owns structural edits to existing files. The model specifies intent/content; OLYMPUS resolves and validates the source mutation.

### AgentVerifier
Owns syntax and targeted test verification. A successful write is not task success.

## Failure contract

- `COMPLETED`: requested step verified successfully.
- `RETRYING`: action or verification failure is recoverable inside the current bounded attempt.
- `BLOCKED`: runtime cannot safely continue this attempt (budget, policy, or technical model failure).
- `FAILED`: semantic/logical failure that should not be retried as infrastructure failover.

Technical model failover is owned by `AutonomousPatchRunner`, not duplicated in `AgentLoop` or shell scripts.

## Runtime generations

V2 (`mission.py`, `loop.py`, structured actions) is canonical for autonomous patch execution.

V1 (`dev_agent.py`, `orchestrator.py`, `edit_agent.py`, acceptance-test generator, legacy CLI) remains temporarily for compatibility with the desktop interactive flow. New autonomous capabilities must not be added to V1. V1 should eventually become a thin adapter into V2 or be retired after parity is proven.

## Model policy

Models are replaceable resources. No canonical runtime component may hardcode a provider/model list. `DecisionEngine` supplies preference; `OlympusModelSelector.select_candidates()` supplies ordered eligible candidates.

## Safety

No arbitrary shell action exists in the canonical action contract. Writes are workspace constrained. Destructive commands, dependency installation, migrations, network expansion, and out-of-workspace writes require explicit policy authorization.

## Testing gates

1. focused unit tests for changed contracts;
2. full local regression for milestone/checkpoint;
3. real OmniRoute integration on the Mac;
4. no unexpected skips, failures, errors, or `ResourceWarning` at release sign-off.
