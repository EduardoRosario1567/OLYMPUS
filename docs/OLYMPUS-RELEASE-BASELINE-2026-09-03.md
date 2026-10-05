# OLYMPUS RELEASE BASELINE — 2026-09-03

This package is the consolidated release candidate built from the reconciled OLYMPUS NEXT tree.

## Work validation

- Full unit/integration suite: 412 tests
- Failures: 0
- Errors: 0
- Resource warnings: 0 in the controlled run
- Expected environment-dependent skips: 4 when real localhost OmniRoute is unavailable in the Work sandbox
- Agent Runtime V2 focused tests: PASS
- Autonomous mission focused tests: PASS

## Runtime contract

- AgentLoop owns one bounded model attempt.
- AgentControlPlane owns model candidate failover.
- Mission runner owns logical mission sequencing.
- Technical model failure is retryable through candidate failover.
- Logical failure terminates the mission as FAILED.
- Policy/budget/environment blocks terminate as BLOCKED.
- Context is bounded and selected locally.
- PatchEngine performs deterministic structured edits.
- Models propose actions; the runtime executes them.

## Installation contract

The ZIP contains one root directory named `OLYMPUS`.
Run `python3 scripts/verify_install.py` from that root before executing the suite.
