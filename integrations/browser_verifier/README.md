# Independent static landing-page gate (pilot)

The private HTTP worker receives a checksummed compiled dist manifest from E2B.
It does not install or execute generated packages. Chromium loads those files
from an ephemeral loopback server; all other network requests are denied.
Only static landing pages with internal anchor navigation are supported.
Forms, application controls, media, embedded content, external links and CSS
asset references are rejected. This is intentionally not a general app verifier.

The worker checks 1440x900 and 390x844, document semantics, image loading,
horizontal overflow, readable text contrast, and section navigation. Bounded
repairs choose black/white text colors and reserve space for sticky headers.
It embeds compiled CSS and local images into a static HTML, removes scripts
and event handlers, and retests that exact artifact with JavaScript disabled.
This is a technical gate, not a subjective design approval or WCAG certification.

Deploy the Dockerfile as a private, single-replica pilot service. It reuses the
existing frontend Playwright lockfile. Set PORT and a secret token of at least
24 characters in OLYMPUS_BROWSER_VERIFIER_TOKEN. Backend variables:
OLYMPUS_BROWSER_VERIFIER_URL (private HTTP origin) and the same token.
No public domain is needed. An unavailable worker fails closed.

The adapter preserves original generated sources under source/, publishes the
verified HTML at index.html, and writes docs/browser-verification.json. Runtime
recomputes receipt, HTML, and source checksums before publication. Receipts are
an internal trusted-runner boundary, not signed third-party attestations.
Source/build-only runs still cannot publish. Production and tenant-isolation
guards are unchanged; do not enable the global-state upstream for production.

Checks: python -m unittest tests.test_independent_browser_gate. CI must install
the already declared Playwright browser; missing browser dependencies in CI
fail the test rather than silently skipping independent verification.
