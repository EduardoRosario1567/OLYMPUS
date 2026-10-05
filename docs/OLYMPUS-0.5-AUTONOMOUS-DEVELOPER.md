# OLYMPUS 0.5 — Autonomous Developer

0.5 is an integration milestone, not a new parallel runtime.

A human supplies an objective. The existing runtime owns repository discovery,
context selection, model/provider routing, structured actions, verification,
failover and mission checkpoints. `AutonomousDeveloper` provides one stable
high-level entrypoint and a deterministic final report.

## Contract

- no target file is required from the user;
- one logical AUTO-1 mission represents the objective;
- model/provider failover remains owned by the control plane;
- verified work is reported, not inferred;
- failures are never converted into success;
- resume uses the existing mission checkpoint store;
- user-facing live progress remains one fixed line.
