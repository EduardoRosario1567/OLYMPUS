# OLYMPUS External Validation Queue

Only gates that cannot be proven in the Work environment belong here.

| Gate | Environment | Required evidence | Status |
|---|---|---|---|
| MAC-001 | macOS | `omniroute health` = healthy | PENDING |
| MAC-002 | macOS | `/v1/models` reachable and real models listed | PENDING |
| MAC-003 | macOS | full suite with `RUN_REAL_OMNIROUTE=1 RUN_REAL_AGENT_LOOP=1` = OK | PENDING |
| MAC-004 | macOS | V1 candidate runs side-by-side without modifying verified 0.4 baseline | PENDING |
| DEPLOY-001 | Railway/Vercel | production build + health checks | PENDING |
| IOS-001 | physical iPhone | create mission, leave Safari, return, inspect persisted result | PENDING |
