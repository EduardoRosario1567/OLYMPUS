# Remote sandbox pilot (E2B) — explicit opt-in

This adapter is an *optional executor for Python unittest actions*, not a
complete remote deployment engine. It does not yet generate, preview or
publish Rosales Café. The legacy static mission endpoint remains BLOCKED
until the complete safety and acceptance gates are implemented.

## When available

The OLYMPUS backend can select a remote E2B sandbox instead of locally
installed Docker for **agent RUN_TEST**:

- `OLYMPUS_ISOLATED_AGENT_TESTS=1` — enable isolated tests for cloud missions.
- `OLYMPUS_ISOLATED_TEST_PROVIDER=e2b` — select E2B instead of Docker.
- `OLYMPUS_REMOTE_SANDBOX_AUTHORIZED=1` — explicit authorization for
  remote service usage, network communication, and possible charges.
- `E2B_API_KEY` — supplied by the server secret manager; never committed.
- Optional Python dependency: `e2b` (installed on the backend only).

No one should set these flags on the user's Mac for internal regression
testing. Do not use production credentials or live customer workspaces in
the first external acceptance test.

## Safety contract

A sandbox is not created when authorization/key is absent; there is no
fallback to host Python. The service is asked to disable Internet access
in the sandbox, with a maximum 180-second command timeout and sandbox
expiry. The uploaded ZIP has a fixed file and byte limit and includes
only Python files from approved subtrees, excluding dotfiles, symlinks,
and common credential filenames. Only validated dotted `tests.*`
modules can be executed. The E2B token stays in the **host's SDK
configuration**, not in sandbox environment variables or the uploaded ZIP.

**This is not a claim of zero credential risk**: an arbitrary Python source
file may contain secrets embedded in code. Use a fresh, minimal mission
workspace and review material allowed for upload. Remote cloud execution
may incur billing; test the quota/cost policy before activating.

## Verification achieved without E2B credentials

The GitHub CI validates the argument and permission gates, the ZIP
filtering, the E2B SDK boundary, sandbox teardown, and provider selection
with a stub SDK. The existing Docker proof separately verifies an
agent RUN_TEST inside a Linux sandbox. The E2B *live* service and a real
LLM-to-site mission remain unverified until authorized credentials,
quota, and acceptance evidence are provided.

## Next acceptance milestones

1. Enforce a per-tenant remote cost and concurrency budget at the server
   (an environment flag is not sufficient authorization in production).
2. Add authenticated, tenant-bound remote sandbox creation and teardown.
3. Provide remote file write/build/preview interfaces for React/static sites,
   with versioned artifacts and no global mutable active-sandbox state.
4. Prove real-model generation of Rosales Café, static validation, visual
   browser QA and preservation, with a signed DONE/BLOCKED manifest.
