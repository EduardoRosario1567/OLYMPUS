"""
Olympus Routing Contract — Interfaces e DTOs do contrato de roteamento.

Define o protocolo RoutingAdapter e os DTOs tipados mínimos necessários
para conectar OLYMPUS a engines externas de roteamento.
"""

from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable
from datetime import datetime
from enum import Enum


class ModelCapability(str, Enum):
    """Capacidades de modelo — mapeia para TaskType do core quando necessário."""
    TEXTO = "texto"
    CODIGO = "codigo"
    ARQUITETURA = "arquitetura"
    REVISAO = "revisao"
    IMAGEM = "imagem"
    DOCUMENTACAO = "documentacao"
    TESTES = "testes"
    INTEGRACAO = "integracao"
    RESPOSTA_CURTA = "resposta_curta"
    RESPOSTA_LONGA = "resposta_longa"


@dataclass(frozen=True)
class RoutingModelInfo:
    """Informações de um modelo disponível no engine de roteamento."""
    model_id: str
    provider: str
    capabilities: list[ModelCapability]
    available: bool
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingHealth:
    """Status de saúde do engine de roteamento / provedor."""
    healthy: bool
    provider: Optional[str] = None
    status: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass(frozen=True)
class RoutingExecutionResult:
    """Resultado da execução de um prompt via engine de roteamento."""
    requested_model: str
    actual_model: str
    provider: str
    output: str
    latency_ms: int
    cost: float
    success: bool
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    status: str = "success"  # ExecutionStatus enum value as string


@runtime_checkable
class RoutingAdapter(Protocol):
    """
    Protocolo abstrato para engines de roteamento de modelos.

    Qualquer implementação (OmniRouteAdapter, OpenRouterAdapter,
    DirectProviderAdapter, LocalModelAdapter) deve satisfazer este contrato.

    OLYMPUS CORE importa apenas este protocolo — nunca implementações concretas.
    """

    def list_models(self) -> list[RoutingModelInfo]:
        """Lista todos os modelos disponíveis no engine de roteamento."""
        ...

    def health(self) -> RoutingHealth:
        """Verifica a saúde do engine de roteamento e/ou provedores."""
        ...

    def execute(
        self,
        model_id: str,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ) -> RoutingExecutionResult:
        """
        Executa um prompt no modelo especificado via engine de roteamento.

        Args:
            model_id: ID do modelo solicitado
            prompt: Texto do prompt
            max_tokens: Limite opcional de tokens de saída
            temperature: Temperatura opcional de sampling
            **kwargs: Parâmetros adicionais específicos do engine

        Returns:
            RoutingExecutionResult com o resultado tipado da execução
        """
        ...