"""
Classificador de tarefas — Fase 1.

Implementação heurística (palavras-chave) por design: é plugável e
substituível (princípio 5 — todo agente deve ser substituível) por um
classificador baseado em modelo real quando fizer sentido, sem alterar
o resto do motor.
"""

import re
from olympus.models import TaskType

_PALAVRAS_CHAVE: dict[TaskType, list[str]] = {
    TaskType.CODIGO: ["implementar", "função", "bug", "refatorar", "código", "endpoint", "script"],
    TaskType.ARQUITETURA: ["arquitetura", "design do sistema", "escalabilidade", "estrutura do projeto", "decisão técnica"],
    TaskType.REVISAO: ["revisar", "review", "code review", "avaliar código", "apontar problemas"],
    TaskType.IMAGEM: ["imagem", "gerar imagem", "logo", "ilustração", "banner"],
    TaskType.DOCUMENTACAO: ["documentação", "documentar", "readme", "manual", "guia de uso"],
    TaskType.TESTES: ["teste", "testes unitários", "cobertura", "qa", "casos de teste"],
    TaskType.INTEGRACAO: ["integrar", "api externa", "webhook", "conectar com", "integração"],
}


class TaskClassifier:
    def classify(self, descricao: str) -> TaskType:
        texto = descricao.lower()

        for tipo, palavras in _PALAVRAS_CHAVE.items():
            if any(p in texto for p in palavras):
                return tipo

        # heurística de tamanho para os tipos "genéricos" de texto
        palavras_count = len(re.findall(r"\w+", texto))
        if palavras_count <= 12:
            return TaskType.RESPOSTA_CURTA
        if palavras_count >= 60:
            return TaskType.RESPOSTA_LONGA
        return TaskType.TEXTO
