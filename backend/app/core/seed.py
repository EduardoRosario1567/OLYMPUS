"""
Popula o ModelRegistry no boot do backend.

TODO real: isso deveria vir de uma tabela `modelos` no banco (é literalmente
o que a Fase 1 chama de "Registro de modelos" no MVP original), não de
código hardcoded. Ficou assim porque a Fase 1 implementou o Registry como
objeto Python in-memory, e migrar isso pra tabela é trabalho de persistência
que ainda não foi feito — não é decisão de arquitetura da Fase 2, é dívida
técnica herdada que precisa ser paga antes de produção multi-tenant.
"""

from olympus.models import Modelo, TaskType
from olympus.registry import ModelRegistry


def seed_models(registry: ModelRegistry) -> ModelRegistry:
    registry.registrar(Modelo(
        id="gpt-4o", nome="GPT-4o", provedor="openai",
        capacidades=[TaskType.CODIGO, TaskType.ARQUITETURA, TaskType.REVISAO, TaskType.RESPOSTA_LONGA],
        custo_estimado=8.0, latencia_estimada=2.5, confiabilidade=0.93, prioridade=2,
    ))
    registry.registrar(Modelo(
        id="gpt-4o-mini", nome="GPT-4o mini", provedor="openai",
        capacidades=[TaskType.CODIGO, TaskType.TEXTO, TaskType.RESPOSTA_CURTA, TaskType.DOCUMENTACAO],
        custo_estimado=1.0, latencia_estimada=0.9, confiabilidade=0.81, prioridade=1,
    ))
    registry.registrar(Modelo(
        id="claude-sonnet", nome="Claude Sonnet", provedor="anthropic",
        capacidades=[TaskType.CODIGO, TaskType.ARQUITETURA, TaskType.REVISAO, TaskType.TESTES, TaskType.RESPOSTA_LONGA],
        custo_estimado=6.0, latencia_estimada=1.8, confiabilidade=0.95, prioridade=3,
    ))
    registry.registrar(Modelo(
        id="claude-haiku", nome="Claude Haiku", provedor="anthropic",
        capacidades=[TaskType.TEXTO, TaskType.RESPOSTA_CURTA, TaskType.DOCUMENTACAO],
        custo_estimado=0.5, latencia_estimada=0.5, confiabilidade=0.70, prioridade=1,
    ))
    return registry
