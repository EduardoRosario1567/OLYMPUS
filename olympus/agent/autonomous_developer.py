from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from olympus.agent.mission import AutonomousPatchRunner, MissionResult, MissionSpec, MissionStep
from olympus.agent.mission_checkpoint import MissionCheckpointStore
from olympus.routing.interfaces import RoutingAdapter
from olympus.skills import SkillRegistry


@dataclass(frozen=True)
class DeveloperReport:
    task: str
    status: str
    success: bool
    models_attempted: Tuple[str, ...]
    files_read: Tuple[str, ...]
    files_modified: Tuple[str, ...]
    tests_run: Tuple[str, ...]
    iterations: int
    error: Optional[str] = None
    delivery_review: Optional[dict] = None


class AutonomousDeveloper:
    """High-level targetless development entrypoint.

    Acceptance is owned by the mission runtime.  This wrapper deliberately does
    not implement task-specific regex repairs: a model's finish/blocked status is
    interpreted by AutonomousPatchRunner + AcceptanceContract before a report is
    returned here.
    """

    def __init__(
        self,
        root: str,
        router: RoutingAdapter,
        selector: Optional[Any] = None,
        telemetry: Optional[Callable[[dict], None]] = None,
        checkpoint_store: Optional[MissionCheckpointStore] = None,
        skill_registry: Optional[SkillRegistry] = None,
        skills_fabric: Optional[Any] = None,
    ) -> None:
        self.root = str(Path(root).resolve())
        self.skill_registry = skill_registry or SkillRegistry()
        self.runner = AutonomousPatchRunner(
            self.root,
            router,
            selector=selector,
            telemetry=telemetry,
            checkpoint_store=checkpoint_store,
            skill_registry=self.skill_registry,
        )
        if skills_fabric is not None:
            from olympus.agent.planner import ModelPlanner
            self.runner.planner_factory = lambda adapter, model: ModelPlanner(
                adapter, model, skills_fabric=skills_fabric, telemetry=telemetry,
            )

    @staticmethod
    def mission_for(task: str, max_iterations: int = 12) -> MissionSpec:
        objective = (task or "").strip()
        if not objective:
            raise ValueError("development objective is required")
        return MissionSpec(
            "DEVELOP",
            "Autonomous development objective",
            (MissionStep("AUTO-1", "Investigate, implement and verify", objective, max_iterations),),
            metadata={"mode": "autonomous_developer", "targetless": True},
        )

    def run(self, task: str, max_iterations: int = 12, resume: bool = True) -> DeveloperReport:
        result = self.runner.run(self.mission_for(task, max_iterations), resume=resume)
        return self._report(task, result)

    @staticmethod
    def _report(task: str, result: MissionResult) -> DeveloperReport:
        models = []
        files_read = []
        files_modified = []
        tests_run = []
        iterations = 0
        delivery_review = None
        for step in result.steps:
            models.extend(step.models_attempted or ((step.model,) if step.model else ()))
            state = step.loop_result.state
            files_read.extend(state.files_read)
            files_modified.extend(state.files_modified)
            tests_run.extend(state.tests_run)
            iterations += state.iteration
            delivery_review = state.metadata.get("delivery_review") or delivery_review
        return DeveloperReport(
            task=task,
            status=result.status,
            success=result.success,
            models_attempted=tuple(dict.fromkeys(models)),
            files_read=tuple(dict.fromkeys(files_read)),
            files_modified=tuple(dict.fromkeys(files_modified)),
            tests_run=tuple(dict.fromkeys(tests_run)),
            iterations=iterations,
            error=result.error,
            delivery_review=delivery_review,
        )
