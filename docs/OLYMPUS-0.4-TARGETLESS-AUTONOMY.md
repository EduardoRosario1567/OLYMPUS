# OLYMPUS 0.4 — Targetless Autonomy

The interactive DEV AGENT no longer requires the user to identify a target file before the agent can start.

## Entrypoint

`scripts/olympus_dev.sh` now forwards the natural-language objective directly to `scripts/olympus_task.py`.

## Runtime path

Task → Mission AUTO-1 → AgentControlPlane → AgentLoop → RepoMap/ContextEngine → actions → verification → finish.

## Repository discovery

RepoMap indexes Python and shell entrypoints. Context selection can therefore discover `scripts/olympus_dev.sh` from a natural-language request about the DEV AGENT/OmniRoute without an explicit file path.

## Live execution

The task CLI emits a heartbeat with elapsed time, current stage, selected model and attempt while the autonomous runtime is active.

## Safety

Workspace/action policies remain unchanged. A missing explicit target no longer causes an immediate user prompt; the runtime investigates first. Existing policy/budget blocks remain terminal when appropriate.
