# OLYMPUS Web Runtime 0.2

## Purpose
Expose the same mission contract to Web, future iOS, and future Android clients.

## API
- `POST /missions` — enqueue an isolated mission.
- `GET /missions/{id}` — mission status/result.
- `GET /missions/{id}/events` — operational telemetry for advanced clients.
- `GET /providers/health` — provider availability.
- `/tester/` — mobile-first Web Tester UI.

## Safety
Web missions run in disposable temporary workspaces. The Web Tester does not mutate the host OLYMPUS repository.

## UX
The primary UI shows one fixed live line: `OLYMPUS trabalhando... MM:SS`. Detailed telemetry remains available via API and is not stacked in the main user experience.

## Mobile contract
The API is intentionally client-agnostic so the future iOS and Android apps can use the same endpoints rather than reimplementing agent logic.
