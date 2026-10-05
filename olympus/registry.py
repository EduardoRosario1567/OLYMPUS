"""
Registry de modelos/provedores.
Princípio: nunca prender a arquitetura a um único provedor -> qualquer
modelo de qualquer provedor entra aqui pela mesma interface.
"""

from typing import Optional
from olympus.models import Modelo, TaskType


class ModelRegistry:
    def __init__(self) -> None:
        self._modelos: dict[str, Modelo] = {}
        self._provedores_indisponiveis: set[str] = set()

    def registrar(self, modelo: Modelo) -> None:
        self._modelos[modelo.id] = modelo

    def desativar(self, modelo_id: str) -> None:
        if modelo_id in self._modelos:
            self._modelos[modelo_id].ativo = False

    def ativar(self, modelo_id: str) -> None:
        if modelo_id in self._modelos:
            self._modelos[modelo_id].ativo = True

    def marcar_provedor_indisponivel(self, provedor: str) -> None:
        """Simula/registra uma queda de provedor (ex: erro de API, timeout, rate limit persistente)."""
        self._provedores_indisponiveis.add(provedor)

    def marcar_provedor_disponivel(self, provedor: str) -> None:
        self._provedores_indisponiveis.discard(provedor)

    def provedor_disponivel(self, provedor: str) -> bool:
        return provedor not in self._provedores_indisponiveis

    def listar(self) -> list[Modelo]:
        return list(self._modelos.values())

    def candidatos_para(self, tipo: TaskType) -> list[Modelo]:
        """Retorna todos os modelos ativos que suportam o tipo de tarefa.
        Não filtra por disponibilidade de provedor — isso é responsabilidade
        do decision_engine, que precisa saber quem foi excluído e por quê."""
        return [m for m in self._modelos.values() if m.suporta(tipo)]

    def obter(self, modelo_id: str) -> Optional[Modelo]:
        return self._modelos.get(modelo_id)

    def registrar_resultado_observado(
        self, modelo_id: str, *, success: bool, latency_ms: int = 0, timeout: bool = False
    ) -> None:
        """Update lightweight runtime evidence without external telemetry."""
        modelo = self._modelos.get(modelo_id)
        if modelo is None:
            return
        previous_attempts = modelo.observed_attempts
        modelo.observed_attempts += 1
        if success:
            modelo.observed_successes += 1
        if timeout:
            modelo.observed_timeouts += 1
        if latency_ms > 0:
            if previous_attempts == 0 or modelo.observed_latency_ms <= 0:
                modelo.observed_latency_ms = float(latency_ms)
            else:
                modelo.observed_latency_ms = (
                    modelo.observed_latency_ms * previous_attempts + float(latency_ms)
                ) / modelo.observed_attempts

    def score_capacidade(self, modelo: Modelo, tipo: TaskType) -> float:
        """Deterministic task/capability score; observed evidence refines priors."""
        if tipo in (TaskType.CODIGO, TaskType.TESTES, TaskType.INTEGRACAO):
            base = (
                0.35 * modelo.coding_strength
                + 0.20 * modelo.agentic_strength
                + 0.15 * modelo.tool_use_strength
                + 0.15 * modelo.structured_output_strength
                + 0.15 * modelo.recovery_strength
            )
        elif tipo == TaskType.ARQUITETURA:
            base = (
                0.35 * modelo.reasoning_strength
                + 0.25 * modelo.agentic_strength
                + 0.15 * modelo.coding_strength
                + 0.15 * modelo.recovery_strength
                + 0.10 * modelo.structured_output_strength
            )
        else:
            base = 0.6 * modelo.reasoning_strength + 0.4 * modelo.structured_output_strength
        if modelo.observed_attempts:
            success_rate = modelo.observed_successes / modelo.observed_attempts
            timeout_rate = modelo.observed_timeouts / modelo.observed_attempts
            base = 0.70 * base + 0.30 * max(0.0, success_rate - 0.5 * timeout_rate)
        return max(0.0, min(1.0, base))
