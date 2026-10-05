# OLYMPUS 0.4.5 - AI Fabric Multi-Provider

Status: Work checkpoint PASS.

## Contract

The Agent Runtime depends on routing contracts, never on OmniRoute itself.
Provider identity and model identity are independent.

Initial provider registry supports:
- OmniRoute (existing adapter)
- OpenRouter direct (when OPENROUTER_API_KEY is configured)
- Groq (when GROQ_API_KEY is configured)
- Cerebras (when CEREBRAS_API_KEY is configured)
- Ollama local (health-discovered, no key required)

OpenAI-compatible providers share a generic adapter. Provider health is checked before route ranking.

## API
- GET /providers
- GET /providers/health
- GET /providers/models/ranked

## Next
Model Lab will add observed success, timeout, format compliance, repair success and latency scoring per provider/model route.
