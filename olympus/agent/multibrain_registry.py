"""Zero-cost model routes for the autonomous agent runtime.

OpenRouter free model slugs change frequently. The stable ``openrouter/free``
router selects among the free models that are actually available when each
request is made. OmniRoute exposes provider models with the provider prefix,
so Olympus sends the route as ``openrouter/openrouter/free``.
"""
from dataclasses import dataclass
from typing import Iterable, Optional

from olympus.models import Modelo, TaskType
from olympus.registry import ModelRegistry


FREE_ROUTER_MODEL_ID = "openrouter/openrouter/free"


@dataclass(frozen=True)
class AgentModelRoute:
    id: str
    name: str
    provider: str
    priority: int
    context_window: int = 131072
    tier: str = "free"


def build_multibrain_registry(routes: Optional[Iterable[AgentModelRoute]] = None) -> ModelRegistry:
    registry = ModelRegistry()
    configured = tuple(routes) if routes is not None else (
        AgentModelRoute(
            FREE_ROUTER_MODEL_ID,
            "OpenRouter Free Models Router",
            "openrouter",
            100,
            200000,
        ),
    )
    for route in configured:
        registry.registrar(Modelo(
            id=route.id,
            nome=route.name,
            provedor=route.provider,
            capacidades=[
                TaskType.TEXTO,
                TaskType.CODIGO,
                TaskType.TESTES,
                TaskType.ARQUITETURA,
                TaskType.REVISAO,
                TaskType.DOCUMENTACAO,
                TaskType.INTEGRACAO,
                TaskType.RESPOSTA_CURTA,
                TaskType.RESPOSTA_LONGA,
            ],
            custo_estimado=0.0 if route.tier in {"free", "local"} else 1.0,
            latencia_estimada=0.8,
            confiabilidade=0.86,
            prioridade=route.priority,
            context_window=route.context_window,
            coding_strength=0.90,
            reasoning_strength=0.90,
            agentic_strength=0.88,
            tool_use_strength=0.88,
            recovery_strength=0.88,
            structured_output_strength=0.90,
        ))
    return registry
