# OLYMPUS — Skill × Model × Provider Routing

A routing layer ranks combinations of skill, model and provider without executing the model.

## Flow

`Objective -> SkillResolver -> SkillRoutePlanner -> Control Plane -> AgentLoop`

## Scoring

The planner combines skill fit, task capability, observed Model Lab evidence, provider health and cost policy. Sparse observations remain conservative because Model Lab confidence shrinks them toward neutral.

## Safety

This component is advisory. It does not execute actions and does not bypass SkillPolicy, ActionNormalizer, tenant isolation, sandboxing or the Control Plane.
