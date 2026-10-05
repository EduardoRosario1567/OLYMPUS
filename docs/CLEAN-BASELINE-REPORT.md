# OLYMPUS Clean Baseline Report

## Status

**WORK CHECKPOINT: PASS**

## Input

Reconstructed from `OLYMPUS-CONTEXT-FULL.zip`, including the current Mac environment report and the complete repository state supplied on 2026-09-03.

## Architecture corrections

- Established V2 mission runtime as the canonical autonomy path.
- Defined a single recovery contract and responsibility boundary.
- Added `FailureKind` classification.
- Planner/model technical failures now end one AgentLoop model attempt as `BLOCKED/technical` instead of being confused with semantic failure or repeatedly consuming the same model budget.
- `AutonomousPatchRunner` now owns ordered model failover and can continue a step with the next eligible candidate.
- `OlympusModelSelector` now exposes ordered eligible candidates derived from DecisionEngine preference.
- Missions without explicit STEP sections become one bounded `AUTO-1` objective; explicit STEP missions remain supported.
- Updated regression tests to match the canonical mission contract rather than historical assumptions.
- Removed the obsolete hardcoded `~/Downloads/olympus-repo` path from `scripts/olympus_dev.sh`; project root is resolved from the script location.
- Added reproducible macOS app installer script.
- Added explicit source-of-truth and architecture audit documents.
- Declared core Python dependencies separately from backend dependencies.

## Verification in Work

- Focused clean-runtime tests: PASS.
- Full suite: **409 tests discovered; all executed tests PASS; 4 skipped real-integration tests by environment design.**
- Failures: 0.
- Errors: 0.
- ResourceWarning: 0.
- Python compilation of changed Python modules: PASS.

The four skips require the source Mac's real OmniRoute endpoint and must be executed there before final release sign-off.

## Mac sign-off command

```bash
cd "$HOME/Projects/OLYMPUS"
python3 -m pip install -r requirements-core.txt
RUN_REAL_OMNIROUTE=1 RUN_REAL_AGENT_LOOP=1 PYTHONPATH=. \
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Expected release gate: `409 tests`, `OK`, zero unexpected skip/fail/error/warning.

## Deferred intentionally

Generated demonstration modules remain in `olympus/agent/` for compatibility because existing regression tests import them directly. Moving them to `examples/` should be a dedicated repository-hygiene patch after this clean baseline is signed off; it is not mixed into the runtime recovery repair.
