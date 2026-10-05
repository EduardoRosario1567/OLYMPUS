# OLYMPUS 0.6.4 — Web Release Candidate

## Status
Frontend/API integration implemented and deploy-ready. Full Next.js build was not executed in this environment because npm dependencies are not installed here; the Docker build installs them during image creation.

## User flow
1. Authenticated user opens the mission workspace.
2. The Web client lists tenant-scoped cloud projects.
3. User creates or selects a project.
4. User submits a natural-language mission.
5. API returns an execution ID immediately (HTTP 202).
6. The browser polls persisted execution status/events.
7. A single fixed timer line communicates activity.
8. Terminal status is rendered from persisted runtime state.

## API contracts consumed
- GET /cloud/projects
- POST /cloud/projects
- POST /cloud/missions
- GET /cloud/executions/{id}
- GET /cloud/executions/{id}/events?after=N
- POST /cloud/executions/{id}/cancel
- POST /cloud/executions/{id}/resume

## Security boundary
- Browser sends the bearer token only in Authorization.
- Provider secrets stay server-side.
- Existing tenant checks remain enforced by the Cloud API.
- The Web client never receives a workspace path.

## Deployment
- `backend/Dockerfile` runs FastAPI with a health check.
- `frontend/Dockerfile` builds and runs Next.js.
- `docker-compose.web-rc.yml` provides a local/homologation composition.

A public production deployment still requires HTTPS, durable production database/storage, secret management, rate limiting, observability, and final security hardening.
