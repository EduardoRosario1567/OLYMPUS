"""
Olympus Routing Contract — Abstract interface for external routing engines.

Este módulo define o contrato abstrato (Protocol) que permite conectar OLYMPUS
a engines externas de roteamento (ex: OmniRoute, OpenRouter, provedores diretos,
modelos locais) sem acoplar o OLYMPUS CORE a nenhuma implementação específica.

Princípio: OLYMPUS CORE NÃO IMPORTA OMNIROUTE.
OmniRoute será futuramente apenas uma implementação substituível de RoutingAdapter.
"""

from olympus.routing.interfaces import (
    RoutingAdapter,
    RoutingModelInfo,
    RoutingHealth,
    RoutingExecutionResult,
)
from olympus.routing.omniroute_adapter import OmniRouteAdapter

__all__ = [
    "RoutingAdapter",
    "RoutingModelInfo",
    "RoutingHealth",
    "RoutingExecutionResult",
    "OmniRouteAdapter",
]