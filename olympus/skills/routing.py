"""Skill-aware routing: ranks model/provider combinations for a skill.

This layer does not execute a model. It only resolves skills and ranks eligible
model/provider routes so the Control Plane can make an auditable choice.
"""
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from olympus.models import Modelo, TaskType
from olympus.registry import ModelRegistry
from olympus.routing.model_lab import BenchmarkCategory, ModelLab
from olympus.skills.models import SkillSpec


@dataclass(frozen=True)
class SkillRoute:
    skill_id: str
    provider: str
    model: str
    skill_score: float
    capability_score: float
    observed_score: float
    health_score: float
    cost_score: float
    final_score: float
    reasons: tuple[str, ...] = ()


class SkillRoutePlanner:
    """Ranks routes for resolved skills without making provider calls."""

    _SKILL_BIAS = {
        "coding": ("coding_strength", "agentic_strength", "tool_use_strength", "structured_output_strength"),
        "testing": ("coding_strength", "tool_use_strength", "structured_output_strength", "recovery_strength"),
        "frontend": ("coding_strength", "agentic_strength", "tool_use_strength", "context_window"),
        "backend": ("coding_strength", "agentic_strength", "recovery_strength", "tool_use_strength"),
        "security": ("reasoning_strength", "structured_output_strength", "tool_use_strength", "recovery_strength"),
        "documentation": ("reasoning_strength", "structured_output_strength", "coding_strength"),
        "product-experience": ("reasoning_strength", "agentic_strength", "structured_output_strength", "context_window"),
        "visual-design": ("coding_strength", "agentic_strength", "structured_output_strength", "context_window"),
        "accessibility": ("reasoning_strength", "coding_strength", "structured_output_strength", "tool_use_strength"),
    }

    def __init__(self, registry: ModelRegistry, model_lab: Optional[ModelLab] = None):
        self.registry = registry
        self.model_lab = model_lab or ModelLab()

    def rank(self, skills: Sequence[SkillSpec], *, task_type: TaskType = TaskType.CODIGO,
             routes: Optional[Iterable[tuple[str, str]]] = None,
             health: Optional[dict[str, float]] = None,
             cost: Optional[dict[str, float]] = None) -> tuple[SkillRoute, ...]:
        health = health or {}
        cost = cost or {}
        route_ids = set(routes or ())
        models = [m for m in self.registry.listar() if m.ativo and m.provedor not in self.registry._provedores_indisponiveis]
        if route_ids:
            models = [m for m in models if (m.provedor, m.id) in route_ids or (m.provedor, m.id.split("/", 1)[-1]) in route_ids]

        resolved = tuple(skills)
        if not resolved:
            resolved = (SkillSpec("coding", "Software Coding", "1.0.0", "", (), ()),)

        out: list[SkillRoute] = []
        for model in models:
            for skill in resolved:
                skill_score, reasons = self._skill_fit(model, skill)
                capability = self.registry.score_capacidade(model, task_type)
                category = self._category_for(skill.id, task_type)
                observed = self.model_lab.observed_score(category, model.provedor, model.id)
                health_score = max(0.0, min(1.0, float(health.get(model.provedor, 1.0))))
                cost_score = max(0.0, min(1.0, float(cost.get(model.id, 1.0))))
                final = (
                    0.35 * skill_score
                    + 0.25 * capability
                    + 0.20 * observed
                    + 0.15 * health_score
                    + 0.05 * cost_score
                )
                out.append(SkillRoute(
                    skill_id=skill.id,
                    provider=model.provedor,
                    model=model.id,
                    skill_score=skill_score,
                    capability_score=capability,
                    observed_score=observed,
                    health_score=health_score,
                    cost_score=cost_score,
                    final_score=max(0.0, min(1.0, final)),
                    reasons=tuple(reasons),
                ))
        return tuple(sorted(out, key=lambda r: (-r.final_score, -r.skill_score, r.provider, r.model, r.skill_id)))

    def _skill_fit(self, model: Modelo, skill: SkillSpec) -> tuple[float, list[str]]:
        fields = self._SKILL_BIAS.get(skill.id, ("agentic_strength", "tool_use_strength", "structured_output_strength"))
        values = []
        reasons = []
        for field in fields:
            value = getattr(model, field, 0.0)
            if field == "context_window":
                value = min(1.0, float(value) / 262144.0) if value else 0.0
            else:
                value = float(value)
            values.append(value)
            reasons.append(f"{field}={value:.2f}")
        return (sum(values) / len(values) if values else 0.0, reasons)

    @staticmethod
    def _category_for(skill_id: str, task_type: TaskType) -> BenchmarkCategory:
        mapping = {
            "coding": BenchmarkCategory.CODE_GENERATION,
            "testing": BenchmarkCategory.TEST_REPAIR,
            "frontend": BenchmarkCategory.EXISTING_EDIT,
            "backend": BenchmarkCategory.EXISTING_EDIT,
            "security": BenchmarkCategory.REASONING,
            "documentation": BenchmarkCategory.REASONING,
            "product-experience": BenchmarkCategory.EXISTING_EDIT,
            "visual-design": BenchmarkCategory.CODE_GENERATION,
            "accessibility": BenchmarkCategory.REASONING,
        }
        return mapping.get(skill_id, BenchmarkCategory.CODE_GENERATION)
