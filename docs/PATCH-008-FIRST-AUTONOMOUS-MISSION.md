# PATCH-008-FIRST-AUTONOMOUS-MISSION

## OBJECTIVE

Improve OLYMPUS observability for autonomous missions.

The mission must be completed autonomously.

## REQUIREMENTS

Add a deterministic mission summary capability.

The final mission result must expose:

- mission identifier
- total steps
- completed steps
- failed steps
- blocked steps
- total iterations
- models used
- files modified
- tests executed
- final status

Reuse existing AgentLoop and mission structures.

Do not create duplicate runtime architecture.

Preserve backward compatibility.

## EXECUTION RULES

- inspect existing implementation first
- use repository map/context
- make minimal changes
- modify existing code when appropriate
- create tests when required
- run targeted tests after changes
- repair failures automatically
- continue without asking for confirmation
- never write outside workspace
- do not install dependencies
- do not start another patch

## ACCEPTANCE

Mission passes only if:

1. summary is deterministic
2. existing mission behavior remains compatible
3. tests cover the new summary
4. targeted tests pass
5. runtime reaches FINISH

## FINISH

Return mission status and execution telemetry.
