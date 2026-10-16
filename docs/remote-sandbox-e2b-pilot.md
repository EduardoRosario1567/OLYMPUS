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

## Remote web build prototype (2026-10-16)

Implemented in `scripts/remote_e2b_web_build.py`, separately from
the original Python unittest adapter. It accepts a curated static site
(`workspace/site/index.html`) or a React/Vite project at the workspace
root (`package.json` + `package-lock.json`, with `"build": "vite build"`).

The opt-in Python entrypoint is
`build_and_preserve(workspace, mode, delivery_root, mission_id)`.
It transfers only the limited source types, requests an E2B sandbox
with non-public incoming traffic, installs React dependencies only
when `OLYMPUS_REMOTE_BUILD_NETWORK_AUTHORIZED=1`, builds, downloads
a bounded ZIP and calls the existing OLYMPUS static delivery gate and
SHA-256 manifest preservation. The result is `BUILD_VERIFIED`, **never
the complete mission DONE**.

This output is stored privately with its manifest. The current cloud
project preview session mechanism is a separate service; importing the
artifact into a tenant-owned project and exposing a verified, short-lived
preview URL is **not implemented by this adapter**.

No external E2B call has been authorized/performed in CI. The tests
exercise the lifecycle, build-command wiring, source filters, ZIP
validation and persistence with a fake E2B backend; the existing
Docker test validates isolated Python action execution separately.
The React package installation and Vite compilation are not yet
proven against a live E2B environment.

Operating safeguards: server-side explicit authorization and service key
are mandatory; React outbound dependency download has a separate opt-in.
These environment flags **are not a substitute for per-user budgets and
tenant accounting**, so do not expose this entrypoint to end users until
the authenticated, tenant-scoped controller and quota enforcement exist.
Never upload a workspace containing secrets embedded in source code;
filename filtering alone cannot detect all secrets.
