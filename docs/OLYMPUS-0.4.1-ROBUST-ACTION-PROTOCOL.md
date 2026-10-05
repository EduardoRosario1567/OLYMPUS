# OLYMPUS 0.4.1 — Robust Action Protocol

## Objective
Make the model-output boundary resilient to common structured-action variations without weakening execution safety.

## Contract
Raw model output is treated as untrusted input.

1. Extract candidate JSON locally.
2. Normalize action key aliases (`type`, `action`, `tool`, `operation`, `name`).
3. Normalize target aliases (`target`, `path`, `file`, `filename`, `module`).
4. Normalize payload aliases (`payload`, `arguments`, `args`, `params`, `content`, `input`).
5. Normalize common action aliases (`edit` -> `PATCH_FILE`, `test` -> `RUN_TEST`, etc.).
6. Reject conflicting action declarations.
7. Produce canonical `AgentAction`.
8. All canonical actions still pass through existing autonomy/policy checks before execution.

No shell execution is introduced by normalization.
No model call is added for normalization.
