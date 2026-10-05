# OLYMPUS 0.6.1 — Production Queue Architecture

## Status
PASS — deterministic queue contract verified locally.

## What changed
- SQLite-backed durable queue state with atomic claim.
- Worker leases with expiry and heartbeat renewal.
- Crash recovery requeues only expired RUNNING/VERIFYING jobs.
- Worker infrastructure failures are requeued up to a bounded retry count.
- Execution workspace is preserved across infrastructure retries and resumes.
- Provider/model failures remain the responsibility of the Agent Control Plane.
- Queue execution is separated from the HTTP request lifecycle.

## Guarantees
- Two worker instances cannot claim the same queued execution atomically.
- A live worker renews its lease and is not reclaimed.
- An expired lease becomes claimable again.
- Worker crashes can preserve the workspace for Mission Resume.
- SQLite connections are closed deterministically.

## Scope boundary
This is a durable single-storage queue foundation, not yet a horizontally scalable external queue service. For production multi-instance deployment, the same queue contract can later be backed by PostgreSQL/Redis/SQS/etc. without changing Web/API contracts.
