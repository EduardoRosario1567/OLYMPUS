"""
Motor de decisão — Fase 1.

Regras (conforme especificação):
- tarefas simples -> modelos baratos
- tarefas críticas -> modelos premium (confiabilidade alta)
- urgência -> menor latência
- baixa confiança -> fallback obrigatório
- sempre registrar o motivo da escolha
"""

from olympus.models import Tarefa, Modelo, DecisaoRegistro, TaskType
from olympus.registry import ModelRegistry

CONFIANCA_MINIMA = 0.75  # abaixo disso, força fallback para o próximo candidato


class SemModeloDisponivel(Exception):
    pass


class DecisionEngine:
    def __init__(self, registry: ModelRegistry, confianca_minima: float = CONFIANCA_MINIMA) -> None:
        self.registry = registry
        self.confianca_minima = confianca_minima

    def decidir(self, tarefa: Tarefa) -> DecisaoRegistro:
        if tarefa.tipo is None:
            raise ValueError("Tarefa sem tipo classificado — rode o classifier antes.")

        candidatos = self.registry.candidatos_para(tarefa.tipo)
        if not candidatos:
            raise SemModeloDisponivel(
                f"Nenhum modelo ativo suporta o tipo de tarefa '{tarefa.tipo.value}'."
            )

        ordenados_completo = self._ordenar_por_politica(candidatos, tarefa)
        nomes_avaliados = [m.id for m in ordenados_completo]

        disponiveis = [m for m in ordenados_completo if self.registry.provedor_disponivel(m.provedor)]
        indisponiveis = [m for m in ordenados_completo if m not in disponiveis]

        if not disponiveis:
            provedores = sorted({m.provedor for m in indisponiveis})
            raise SemModeloDisponivel(
                f"Todos os provedores compatíveis com '{tarefa.tipo.value}' estão indisponíveis: {provedores}."
            )

        escolhido, fallback_confianca, motivo = self._escolher_com_fallback(disponiveis, tarefa)

        # o candidato ideal (topo da ordenação completa, ignorando disponibilidade) estava fora do ar?
        provedor_contornado = bool(ordenados_completo) and ordenados_completo[0] in indisponiveis
        if provedor_contornado:
            ideal = ordenados_completo[0]
            motivo = (
                f"Provedor '{ideal.provedor}' indisponível (modelo ideal seria {ideal.id}). "
                f"Usando alternativa compatível: {motivo}"
            )

        fallback_usado = fallback_confianca or provedor_contornado

        escolhido, downgrade_usado, motivo = self._aplicar_limite_custo(
            escolhido, disponiveis, tarefa, motivo
        )

        if downgrade_usado:
            decisao_status = "downgraded"
        elif fallback_usado:
            decisao_status = "fallback"
        else:
            decisao_status = "approved"

        return DecisaoRegistro(
            tarefa_id=tarefa.id,
            modelo_escolhido=escolhido.id if escolhido else None,
            candidatos_avaliados=nomes_avaliados,
            motivo=motivo,
            fallback_usado=fallback_usado,
            downgrade_usado=downgrade_usado,
            decisao_status=decisao_status,
            confianca=escolhido.confiabilidade if escolhido else 0.0,
            custo_estimado=escolhido.custo_estimado if escolhido else 0.0,
            latencia_estimada_ms=int((escolhido.latencia_estimada if escolhido else 0) * 1000),
        )

    def _ordenar_por_politica(self, candidatos: list[Modelo], tarefa: Tarefa) -> list[Modelo]:
        """Define a ordem de preferência conforme a política ativa para a tarefa."""
        if tarefa.urgente:
            # velocidade primeiro: menor latência
            return sorted(candidatos, key=lambda m: (m.latencia_estimada, -m.confiabilidade))
        if tarefa.critica:
            # confiabilidade primeiro (modelo "premium")
            return sorted(candidatos, key=lambda m: (-m.confiabilidade, -m.prioridade, m.custo_estimado))
        # tarefa simples/padrão: custo primeiro
        return sorted(candidatos, key=lambda m: (m.custo_estimado, -m.confiabilidade))

    def _escolher_com_fallback(
        self, ordenados: list[Modelo], tarefa: Tarefa
    ) -> tuple[Modelo | None, bool, str]:
        for i, modelo in enumerate(ordenados):
            if modelo.confiabilidade >= self.confianca_minima:
                if i == 0:
                    motivo = self._motivo_base(modelo, tarefa)
                else:
                    motivo = (
                        f"Fallback: {ordenados[0].id} descartado por confiabilidade baixa "
                        f"({ordenados[0].confiabilidade:.2f} < {self.confianca_minima}). "
                        f"Escolhido {modelo.id} ({self._motivo_base(modelo, tarefa)})."
                    )
                return modelo, i > 0, motivo

        # nenhum candidato atinge a confiança mínima -> usa o melhor disponível mesmo assim,
        # mas registra claramente o risco (nunca falha silenciosamente)
        melhor = ordenados[0]
        motivo = (
            f"ALERTA: nenhum candidato atingiu confiança mínima ({self.confianca_minima}). "
            f"Usando o melhor disponível: {melhor.id} (confiabilidade {melhor.confiabilidade:.2f})."
        )
        return melhor, True, motivo

    def _aplicar_limite_custo(
        self,
        escolhido: Modelo | None,
        ordenados: list[Modelo],
        tarefa: Tarefa,
        motivo_atual: str,
    ) -> tuple[Modelo | None, bool, str]:
        """
        Regra: custo acima do limite -> downgrade de modelo.
        Roda depois da seleção normal (política + fallback de confiança).
        Busca, entre os candidatos restantes, o mais barato que caiba no
        limite E ainda atinja a confiança mínima. Se nenhum couber, mantém
        o escolhido original e registra o alerta (nunca falha silenciosamente).
        """
        if escolhido is None or tarefa.limite_custo is None:
            return escolhido, False, motivo_atual

        if escolhido.custo_estimado <= tarefa.limite_custo:
            return escolhido, False, motivo_atual

        candidatos_dentro_do_limite = [
            m for m in ordenados
            if m.custo_estimado <= tarefa.limite_custo and m.confiabilidade >= self.confianca_minima
        ]

        if not candidatos_dentro_do_limite:
            motivo = (
                f"{motivo_atual} ALERTA: custo estimado ({escolhido.custo_estimado}) excede o "
                f"limite da tarefa ({tarefa.limite_custo}), mas nenhum candidato dentro do "
                f"orçamento atinge a confiança mínima ({self.confianca_minima}). Mantendo {escolhido.id}."
            )
            return escolhido, False, motivo

        # entre os que cabem no orçamento, pega o mais barato (mantendo o critério de custo)
        substituto = min(candidatos_dentro_do_limite, key=lambda m: m.custo_estimado)
        motivo = (
            f"Downgrade: {escolhido.id} custaria {escolhido.custo_estimado}, acima do limite "
            f"({tarefa.limite_custo}) da tarefa. Substituído por {substituto.id} "
            f"(custo {substituto.custo_estimado}, confiabilidade {substituto.confiabilidade:.2f})."
        )
        return substituto, True, motivo

    @staticmethod
    def _motivo_base(modelo: Modelo, tarefa: Tarefa) -> str:
        if tarefa.urgente:
            return f"selecionado por menor latência ({modelo.latencia_estimada}s)"
        if tarefa.critica:
            return f"selecionado por maior confiabilidade ({modelo.confiabilidade:.2f}), tarefa crítica"
        return f"selecionado por menor custo ({modelo.custo_estimado}), tarefa padrão"
