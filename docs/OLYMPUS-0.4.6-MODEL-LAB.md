# OLYMPUS 0.4.6 — Model Lab

Empirical ranking layer for model+provider routes.

Benchmarks: action protocol, repo discovery, code generation, existing edit, test repair, reasoning, long horizon.

Metrics: attempts, success/timeout rates, action compliance, repair success, average latency, p95 latency, sample confidence.

Sparse evidence is shrunk toward a neutral prior so one lucky result cannot dominate mature evidence. The same model is scored independently for each provider route.

Routing score combines capability prior, observed evidence, provider health, and cost policy.

Benchmarks must execute only in disposable workspaces; ModelLab itself never mutates project files.
