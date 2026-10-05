# OLYMPUS 0.6 — Cloud Runtime

This stage introduces a persistent asynchronous execution boundary for Web, iOS and Android clients.

## Contracts

- `POST /cloud/missions` returns `202` and an `execution_id`.
- `GET /cloud/executions/{id}` returns durable execution state.
- `GET /cloud/executions/{id}/events` returns append-only events with `after` cursor.
- `POST /cloud/executions/{id}/cancel` requests cancellation.
- `POST /cloud/executions/{id}/resume` requeues terminal resumable work.

## Isolation

Each execution receives its own temporary directory below `.olympus/cloud/workspaces/<generated-id>`. The workspace is removed after execution. Mission resume is delegated to the existing `MissionCheckpointStore` inside that workspace.

## Persistence

Execution records and events live in `.olympus/cloud/cloud_runtime.sqlite3`. `RUNNING`/`VERIFYING` records are recovered to `QUEUED` on process restart so verified mission checkpoints can safely replay the active work.

## Product rule

The browser receives an execution identifier immediately. A mission is never coupled to an open HTTP request or an open browser tab.
