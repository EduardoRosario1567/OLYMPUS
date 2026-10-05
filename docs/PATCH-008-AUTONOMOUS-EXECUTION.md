# PATCH-008 — AUTONOMOUS PATCH EXECUTION

## STEP 008.1 — Mission ingestion
Use a persistent Markdown mission specification with explicit STEP sections. Parse it locally; do not spend an LLM call to discover the step boundaries.

## STEP 008.2 — Autonomous step execution
For each mission step, select a model through the existing DecisionEngine path, create a ModelPlanner, and run the AgentLoop until a terminal state. Continue to the next step automatically only after COMPLETED.

## STEP 008.3 — Observable telemetry
Emit machine-readable operational checkpoints for mission start/end, step start/end, model selection, iterations, files modified, tests run, and blocking errors. Do not expose chain-of-thought.

## STEP 008.4 — Safe stopping
Stop the mission on FAILED or BLOCKED. Preserve the completed step results and the exact error. Never ask the user to say "continue" between successful steps.

## STEP 008.5 — CLI
Provide a non-interactive CLI that accepts a mission file and runs it from the project root using OmniRoute. Exit 0 only when every step reaches COMPLETED.
