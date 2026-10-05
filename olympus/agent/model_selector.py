from typing import Any
import json

from olympus.classifier import TaskClassifier
from olympus.agent.multibrain_registry import build_multibrain_registry
from olympus.decision_engine import DecisionEngine
from olympus.models import Tarefa, TaskType


class ModelSelectionError(RuntimeError):
    pass


class OlympusModelSelector:
    def __init__(self, routes=None) -> None:
        self.registry = build_multibrain_registry(routes)
        self.classifier = TaskClassifier()

        try:
            self.engine = DecisionEngine(self.registry)
        except TypeError:
            self.engine = DecisionEngine()

    def _classify(self, task: str) -> Any:
        for name in ("classificar", "classify"):
            method = getattr(self.classifier, name, None)
            if method is None:
                continue

            try:
                return method(task)
            except TypeError:
                continue

        raise ModelSelectionError(
            "TaskClassifier classification method not found"
        )

    @staticmethod
    def _contract_payload(task: str):
        prefix = "OLYMPUS_EXECUTION_CONTRACT\n"
        if not str(task or "").startswith(prefix):
            return None
        try:
            payload = json.loads(str(task)[len(prefix):])
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _build_task(self, task: str) -> Tarefa:
        contract = self._contract_payload(task)
        classification = self._classify(task if contract is None else str(contract.get("objective") or task))
        task_type = getattr(
            classification,
            "tipo",
            getattr(classification, "task_type", classification),
        )
        if contract is not None:
            family = str(contract.get("task_family") or "").lower()
            task_type = {
                "file_operation": TaskType.CODIGO,
                "web": TaskType.CODIGO,
                "application": TaskType.ARQUITETURA,
                "game": TaskType.CODIGO,
                "mathematics": TaskType.RESPOSTA_CURTA,
                "data_analysis": TaskType.REVISAO,
                "research": TaskType.RESPOSTA_LONGA,
                "writing": TaskType.TEXTO,
                "software": TaskType.CODIGO,
            }.get(family, task_type)
        elif self.classifier.has_software_build_intent(task):
            task_type = TaskType.CODIGO
        task_lower = (str(contract.get("objective") or task) if contract else task).lower()
        build_actions = (
            "faça", "faca", "construa", "construir", "desenvolva", "desenvolver",
            "monte", "montar", "crie", "criar",
        )
        software_artifacts = (
            "interface", "frontend", "front-end", "página", "pagina", "site",
            "aplicativo", "app", "componente", "tela", "dashboard", "endpoint",
        )
        code_intent = (
            ".py" in task_lower
            or "patch-" in task_lower
            or "olympus/" in task_lower
            or "agent runtime" in task_lower
            or "agentloop" in task_lower
            or any(token in task_lower for token in (
                "implemente", "implement ", "crie", "create ",
                "modifique", "modify ", "corrija", "fix ",
                "funcao", "função", "classe",
            ))
            or (
                any(action in task_lower for action in build_actions)
                and any(artifact in task_lower for artifact in software_artifacts)
            )
        )
        long_form_types = {TaskType.TEXTO, TaskType.RESPOSTA_CURTA}
        resposta_longa = getattr(TaskType, "RESPOSTA_LONGA", None)
        if resposta_longa is not None:
            long_form_types.add(resposta_longa)
        if task_type in long_form_types and code_intent:
            task_type = TaskType.CODIGO

        from uuid import uuid4
        return Tarefa(
            id=str(uuid4()),
            projeto_id=str(uuid4()),
            descricao=task,
            tipo=task_type,
        )

    def decision(self, task: str):
        return self.engine.decidir(self._build_task(task))

    def select(self, task: str) -> str:
        decision = self.decision(task)
        model = decision.modelo_escolhido
        if model is None:
            raise ModelSelectionError("DecisionEngine returned no selected model")
        return str(model)

    def select_candidates(self, task: str):
        """Return eligible models in DecisionEngine preference order.

        The selected model is always first. Remaining candidates are fallbacks.
        Provider availability and active flags are respected here so runtime
        failover does not retry known-unavailable candidates.
        """
        decision = self.decision(task)
        ordered = []
        if decision.modelo_escolhido:
            ordered.append(decision.modelo_escolhido)
        for model_id in decision.candidatos_avaliados:
            if model_id in ordered:
                continue
            model = self.registry.obter(model_id)
            if model is None or not model.ativo:
                continue
            if not self.registry.provedor_disponivel(model.provedor):
                continue
            ordered.append(model_id)
        if not ordered:
            raise ModelSelectionError("DecisionEngine returned no eligible models")
        return tuple(ordered)
