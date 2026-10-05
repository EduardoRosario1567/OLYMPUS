# OLYMPUS 0.4.3 - Multi-Brain Model Pool

## Goal
Reduce dependence on a two-model pool and route autonomous coding work using a FREE, capability-aware set of model candidates.

## Agent pool
- `openrouter/qwen/qwen3-coder:free`
- `openrouter/mistralai/devstral-2512:free`
- `openrouter/z-ai/glm-4.5-air:free`
- `openrouter/cohere/north-mini-code:free`
- `openrouter/nvidia/nemotron-3.5-lightning:free`

The legacy closed-loop registry remains unchanged for backward compatibility. The autonomous agent owns a separate multi-brain registry.

## Capability matrix
`Modelo` now supports routing priors for context window, coding, reasoning, agentic behavior, tool use, recovery and structured output. It also stores lightweight observed runtime evidence (attempts, successes, timeouts and mean latency).

## Routing
For equal-cost candidates, the DecisionEngine ranks by task capability fit, then reliability and manual priority. Runtime evidence can refine the capability score without changing provider integrations.

## Evidence
Full Work regression: 431 tests, 0 failures, 0 errors, 4 real-environment skips.
