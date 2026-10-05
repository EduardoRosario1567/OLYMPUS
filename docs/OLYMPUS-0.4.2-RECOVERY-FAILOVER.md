# OLYMPUS 0.4.2 — Recovery + Model Failover

Status: PASS in Work.

## Contract
- AgentLoop owns one bounded model attempt.
- AgentControlPlane owns model failover.
- Technical failures (timeout, 429, provider/unavailable/connection) may move to the next eligible model.
- Logical failures do not trigger model failover.
- Progress already achieved by a technically interrupted attempt is checkpointed into the next model attempt: iteration count, files read/modified, tests run, observations, and errors.
- Mission step identity remains singular; model attempts live in telemetry.

## Verification
- Focused recovery/control-plane/mission tests: PASS.
- Full suite: 427 tests, PASS, 4 environment-gated real OmniRoute skips in Work.
- ResourceWarning treated as error: PASS.
