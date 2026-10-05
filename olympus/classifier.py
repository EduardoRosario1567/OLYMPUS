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
    _SOFTWARE_BUILD_ACTIONS = (
        "crie", "criar", "construa", "construir", "desenvolva", "desenvolver",
        "gere", "gerar", "monte", "montar", "implemente", "implementar",
        "create", "build", "develop", "generate", "implement",
    )
    _SOFTWARE_ARTIFACTS = (
        "landing page", "interface web", "interface", "frontend", "front-end",
        "página web", "pagina web", "website", "site", "aplicativo", "dashboard",
        "componente", "tela", "endpoint", "api",
    )
    _AGENT_CODE_INTENT_RULES = (
        "crie uma constante",
        "criar uma constante",
        "adicione uma função",
        "adicionar uma função",
        "crie uma função",
        "implemente uma função",
        "implemente um módulo",
        "implementar um módulo",
        "corrija este arquivo",
        "corrigir este arquivo",
        "modifique este arquivo",
        "modificar este arquivo",
        "create a constant",
        "add a function",
        "create a function",
        "implement a module",
        "implement a function",
        "fix this file",
        "modify this file",
    )

    @classmethod
    def has_software_build_intent(cls, descricao: str) -> bool:
        """Recognize builds before ambiguous terms such as 'trabalho manual'."""
        text = str(descricao or "").lower()
        has_action = any(
            re.search(r"(?<!\w)%s(?!\w)" % re.escape(action), text)
            for action in cls._SOFTWARE_BUILD_ACTIONS
        )
        has_artifact = any(
            re.search(r"(?<!\w)%s(?!\w)" % re.escape(artifact), text)
            for artifact in cls._SOFTWARE_ARTIFACTS
        )
        return has_action and has_artifact


    def classify(self, descricao: str) -> TaskType:

        descricao_norm = descricao.lower().strip()

        # A software deliverable wins over incidental documentation/review
        # vocabulary contained inside its product brief.
        if self.has_software_build_intent(descricao_norm):
            return TaskType.CODIGO

        if any(
            rule in descricao_norm
            for rule in self._AGENT_CODE_INTENT_RULES
        ):
            return TaskType.CODIGO

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
