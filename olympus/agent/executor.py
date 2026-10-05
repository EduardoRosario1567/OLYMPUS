from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.autonomy import AutonomyDecision, AutonomyPolicy
from olympus.agent.patch_engine import PatchEngine, PatchRequest
from olympus.agent.safe_apply import apply
from olympus.agent.test_runner import TargetedTestRunner
from olympus.agent.delivery_sources import DeliverySources


@dataclass(frozen=True)
class ActionObservation:
    success: bool
    action: AgentAction
    output: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)


class ActionExecutor:
    DEFAULT_ALLOWED_PATHS = (
        "olympus/", "tests/", "scripts/", "app/", "src/", "public/",
        "frontend/", "backend/", "docs/", "assets/", "styles/",
        "attachments/", "imports/", "index.html", "README.md", "package.json",
    )

    def __init__(self, root: str, allowed_paths=DEFAULT_ALLOWED_PATHS, autonomy_policy=None) -> None:
        self.root = Path(root).resolve()
        self.allowed_paths = tuple(allowed_paths)
        self.autonomy = autonomy_policy or AutonomyPolicy()
        self.patch_engine = PatchEngine(str(self.root), self.allowed_paths)
        self.test_runner = TargetedTestRunner(str(self.root))

    def _safe_path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError:
            raise ValueError("path escapes workspace")
        return path

    def execute(self, action: AgentAction) -> ActionObservation:
        policy = self.autonomy.evaluate(action)
        if policy.decision != AutonomyDecision.ALLOW:
            return ActionObservation(False, action, error=policy.reason, metadata={"autonomy": policy.decision.value})
        try:
            if action.type == ActionType.READ_FILE:
                output = self._safe_path(action.target).read_text(encoding="utf-8")
            elif action.type == ActionType.RESEARCH_SOURCES:
                output = DeliverySources().search(action.target, action.payload)
            elif action.type == ActionType.SEARCH_CODE:
                query = str(action.payload or "")
                output = []
                source_suffixes = {".py", ".sh", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".json", ".md", ".txt", ".csv", ".xml", ".yaml", ".yml", ".sql"}
                for path in self.root.rglob("*"):
                    if not path.is_file() or path.suffix.lower() not in source_suffixes:
                        continue
                    rel = path.relative_to(self.root).as_posix()
                    if any(part in {".git", ".olympus", ".venv", "venv", "node_modules", "__pycache__"} for part in Path(rel).parts):
                        continue
                    for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if query in line:
                            output.append((rel, number, line.strip()))
                            if len(output) >= 50:
                                break
                    if len(output) >= 50:
                        break
            elif action.type == ActionType.CREATE_FILE:
                content = str(action.payload or "")
                payload = "=== FILE: %s ===\n%s" % (action.target, content)
                output = apply(str(self.root), payload, [action.target])
            elif action.type == ActionType.PATCH_FILE:
                data = dict(action.payload or {})
                output = self.patch_engine.apply(PatchRequest(file=action.target, **data))
            elif action.type == ActionType.RUN_TEST:
                modules = action.payload if isinstance(action.payload, (list, tuple)) else [str(action.payload)]
                output = self.test_runner.run_unittest(modules)
                if not output.success:
                    return ActionObservation(False, action, output=output, error=output.stderr or output.stdout)
            elif action.type == ActionType.INSPECT_RESULT:
                output = {"statement": action.payload, "verification": "model_statement_only",
                          "browser_verified": False, "visual_reviewed": False}
            elif action.type == ActionType.FINISH:
                output = action.payload or "finished"
            else:
                return ActionObservation(False, action, error="unsupported action")
            return ActionObservation(True, action, output=output)
        except Exception as exc:
            return ActionObservation(False, action, error=str(exc))
