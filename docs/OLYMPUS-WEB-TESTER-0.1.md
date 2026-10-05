# OLYMPUS Web Tester 0.1

Mobile-first validation UI for browser/iPhone testing.

## Product contract
- Web is a validation/client surface, not the agent engine.
- Runtime remains behind an API/sandbox boundary.
- One fixed live-processing line with timer; no stacked execution chatter.
- No provider credentials in browser storage.
- Same future API contracts should be consumable by Web, iOS, Android and desktop clients.

## Next integration
1. POST /api/missions
2. GET /api/missions/{id}
3. SSE/WebSocket /api/missions/{id}/events
4. GET /api/providers/health
5. GET /api/models/ranked
