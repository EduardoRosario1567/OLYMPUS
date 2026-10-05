# OLYMPUS Architecture Audit — Clean Baseline

## Findings

### Confirmed strengths

- Model-agnostic routing contract exists.
- Decision, execution result, and quality evaluation are separated.
- RepoMap and ContextEngine bound model context deterministically.
- Action contract prevents direct arbitrary shell execution by the model.
- PatchEngine supports structural existing-file mutation with syntax validation.
- AgentLoop is bounded and prevents infinite loops.
- Mission runner supports explicit multi-step missions and implicit `AUTO-1` missions.
- Real OmniRoute and Judge integration have been proven on the source Mac in prior gates.

### Root causes of the recent loop

1. **Recovery ownership was duplicated.** V1 CLI, AgentLoop, and MissionRunner each had partial retry/fallback behavior.
2. **Tests followed moving assumptions.** Expected terminal states changed before a stable failure contract existed.
3. **V1 and V2 coexist in the same agent package without a documented canonical boundary.**
4. **Operational path drift existed.** `scripts/olympus_dev.sh` still hardcoded the former Downloads checkout.
5. **Mission semantics changed without updating regression tests.** `AUTO-1` became valid while a test still required explicit STEPs.
6. **Model selection exposed only one model**, making runtime failover awkward even though DecisionEngine already knew candidate order.
7. **Generated demonstration modules live inside `olympus/agent/`.** They are not runtime architecture and should be migrated to examples later, only after compatibility is intentionally handled.

## Clean-baseline decisions

- V2 mission runtime is canonical for autonomy.
- MissionRunner owns model failover.
- AgentLoop owns one model attempt and bounded action/verification retry.
- Technical planner/model failure is `BLOCKED` + `failure_kind=technical`, not `FAILED` and not repeated against the same model.
- DecisionEngine remains the source of model preference; selector exposes ordered candidates.
- Explicit STEPs remain supported; a mission without STEPs becomes one bounded `AUTO-1` objective.
- V1 is compatibility-only and receives no new autonomous architecture.

## Deferred cleanup

The generated/demo files currently in `olympus/agent/` should move to `examples/` in a dedicated hygiene patch. They are intentionally left in place in this baseline because several regression tests import them directly. Moving them during the recovery-contract reset would mix architecture repair with unrelated compatibility churn.
