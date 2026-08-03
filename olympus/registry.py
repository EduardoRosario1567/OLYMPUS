"""
Registry de modelos/provedores.
Princípio: nunca prender a arquitetura a um único provedor -> qualquer
modelo de qualquer provedor entra aqui pela mesma interface.
"""

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

    def obter(self, modelo_id: str) -> Modelo | None:
        return self._modelos.get(modelo_id)
