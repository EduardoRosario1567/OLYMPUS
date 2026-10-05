from dataclasses import dataclass
import json
from typing import Any, Callable, Optional, Tuple

from olympus.agent.actions import ActionType, IDEMPOTENT_GUARDED_ACTIONS
from olympus.agent.acceptance import format_failures
from olympus.agent.context_engine import ContextEngine
from olympus.agent.executor import ActionExecutor, ActionObservation
from olympus.agent.recovery import FailureKind, classify_failure
from olympus.agent.repo_map import build_repo_map
from olympus.agent.state import AgentState, AgentStatus
from olympus.agent.verifier import AgentVerifier


@dataclass(frozen=True)
class AgentLoopResult:
    state: AgentState
    history: Tuple[dict, ...]

    @property
    def failure_kind(self) -> Optional[str]:
        return self.state.metadata.get("failure_kind")


class AgentLoop:
    """Bounded PLAN -> ACT -> OBSERVE -> VERIFY loop.

    Contract:
    - model/planner technical failures stop this model attempt as BLOCKED/technical;
      model failover belongs to the mission/runtime boundary, not to this loop.
    - action/verification failures are retryable inside the same loop budget.
    - semantic planner failures are FAILED.
    - iteration exhaustion is BLOCKED/budget.
    """

    def __init__(
        self,
        root: str,
        planner: Any,
        executor: Optional[ActionExecutor] = None,
        verifier: Optional[AgentVerifier] = None,
        context_engine: Optional[ContextEngine] = None,
        skill_policy: Optional[Any] = None,
        skill_context: Optional[dict] = None,
        progress_callback: Optional[Callable[[AgentState], None]] = None,
        acceptance_contract: Optional[Any] = None,
    ) -> None:
        self.root = root
        self.planner = planner
        self.executor = executor or ActionExecutor(root)
        self.verifier = verifier or AgentVerifier(root)
        self.context_engine = context_engine or ContextEngine(root)
        self.skill_policy = skill_policy
        self.skill_context = dict(skill_context or {})
        self.progress_callback = progress_callback
        self.acceptance_contract = acceptance_contract

    def _report_progress(self, state: AgentState) -> None:
        """Persist portable state at action boundaries when a mission owns us."""
        if self.progress_callback is not None:
            self.progress_callback(state)

    def _metadata(self, state: AgentState, **updates: Any) -> dict:
        metadata = dict(state.metadata)
        metadata.update(updates)
        if "OLYMPUS_WEB_DELIVERY_V1" in state.task:
            metadata["delivery_review"] = getattr(self.verifier, "delivery_review", None) or {
                "profile": "web-v1", "scope": "static_checks_only", "browser": "pending", "visual": "not_assessed"}
        return metadata

    def _acceptance(self, state: AgentState):
        contract = self.acceptance_contract
        if contract is None or not getattr(contract, "has_explicit_checks", False):
            return True, (), []
        results, _ctx = contract.verify(state.files_modified)
        failures = tuple(
            "acceptance: %s" % line
            for line in format_failures(results).splitlines()
            if line.strip()
        )
        return not failures, failures, results

    @staticmethod
    def _state_summary(state: AgentState, skill_context: Optional[dict] = None) -> str:
        recent = []
        for observation in state.observations[-3:]:
            action = getattr(observation, "action", None)
            action_type = getattr(getattr(action, "type", None), "value", None)
            item = {
                "action": action_type,
                "target": getattr(action, "target", None),
                "success": bool(getattr(observation, "success", False)),
                "error": str(getattr(observation, "error", "") or "")[:300],
            }
            target = str(getattr(action, "target", "") or "")
            internal = ".olympus" in target.replace("\\", "/").split("/")
            sensitive = any(part.startswith(".env") for part in target.split("/"))
            if not internal and not sensitive and item["success"]:
                output = getattr(observation, "output", None)
                if action_type == ActionType.SEARCH_CODE.value:
                    rows = output if isinstance(output, (list, tuple)) else ()
                    item["query"] = str(getattr(action, "payload", "") or "")[:160]
                    item["output"] = [
                        [str(row[0])[:160], row[1], str(row[2])[:160]]
                        for row in rows[:4]
                        if isinstance(row, (list, tuple)) and len(row) >= 3
                    ]
                    item["output_truncated"] = len(rows) > 4 or any(
                        len(str(row[2])) > 160 for row in rows[:4]
                        if isinstance(row, (list, tuple)) and len(row) >= 3
                    )
                elif action_type == ActionType.READ_FILE.value:
                    item["output"] = str(output or "")[:2400]
                    item["output_truncated"] = len(str(output or "")) > 2400
                    item["read_range"] = dict(getattr(observation, "metadata", {}).get("read_range") or {})
                    if item["output_truncated"] or item["read_range"].get("next_start_line"):
                        item["continuation"] = "Read the remaining lines using payload {start_line, max_lines}; omitted text is not evidence."
                elif action_type == ActionType.RESEARCH_SOURCES.value and isinstance(output, dict):
                    item["output"] = dict(output, results=[
                        {key: (str(value)[:180] if key in ("description", "excerpt", "author") else value)
                         for key, value in row.items()}
                        for row in output.get("results", [])[:2]
                    ])
            recent.append(item)
        summary = {
            "status": state.status.value,
            "iteration": state.iteration,
            "files_read": list(state.files_read),
            "files_modified": list(state.files_modified),
            "tests_run": list(state.tests_run),
            "recent_actions": recent,
            "recent_errors": [str(item)[:600] for item in state.errors[-3:]],
            "model_handoffs": list(state.metadata.get("model_handoffs") or ())[-3:],
            "completed_action_keys": list(
                state.metadata.get("completed_action_keys") or ()
            )[-24:],
            "completion_rule": "If the requested result is already complete, return the finish action now.",
            "delivery_review": {
                key: (state.metadata.get("delivery_review") or {}).get(key)
                for key in ("scope", "browser", "layout", "visual", "content_sha256")
            } if state.metadata.get("delivery_review") else None,
            "execution_directive": (
                "Repair only the reported errors in the existing files, then verify."
                if state.files_modified and state.errors else
                "Verify the existing deliverable and finish; do not recreate completed work."
                if state.files_modified else
                "Follow the delivery concept and produce the complete requested result; verify it before finish."
            ),
        }
        if skill_context:
            summary["professional_skill_contract"] = skill_context
        return json.dumps(summary, ensure_ascii=False)

    def run(
        self,
        task: str,
        task_type: str = "codigo",
        selected_model: Optional[str] = None,
        max_iterations: int = 12,
        initial_state: Optional[AgentState] = None,
    ) -> AgentLoopResult:
        if initial_state is None:
            state = AgentState(
                task=task,
                task_type=task_type,
                selected_model=selected_model,
                max_iterations=max_iterations,
            )
        else:
            state = initial_state.resume_for_model(selected_model or initial_state.selected_model or "")
            remaining_budget=state.metadata.get("next_model_iteration_budget")
            if remaining_budget is not None:
                resumed_metadata=dict(state.metadata)
                resumed_metadata.pop("next_model_iteration_budget",None)
                state=AgentState(
                    task=state.task,
                    task_type=state.task_type,
                    status=state.status,
                    iteration=state.iteration,
                    max_iterations=max(1,int(remaining_budget)),
                    selected_model=state.selected_model,
                    current_action=state.current_action,
                    files_read=state.files_read,
                    files_modified=state.files_modified,
                    tests_run=state.tests_run,
                    observations=state.observations,
                    errors=state.errors,
                    quality_score=state.quality_score,
                    final_confidence=state.final_confidence,
                    metadata=resumed_metadata,
                )
        repo_map = build_repo_map(self.root)
        history = []
        available = tuple(ActionType)

        # A resumed mission may already contain a complete result produced by
        # the previous model. Verify it before spending a single additional
        # provider token.
        if initial_state is not None and state.files_modified:
            verification = self.verifier.verify(state.files_modified, state.tests_run)
            acceptance_ok, acceptance_errors, acceptance_results = self._acceptance(state)
            quality_errors = self.verifier.verify_task_deliverable(
                task,
                state.files_modified,
                tuple(self.skill_context.get("ids", ())),
            )
            if verification.passed and not quality_errors and acceptance_ok:
                state = state.transition(
                    AgentStatus.COMPLETED,
                    final_confidence=verification.report.confidence,
                    metadata=self._metadata(
                        state,
                        verification=verification.report.to_dict(),
                        completion_reason="verified_before_model_resume",
                        active_skills=list(self.skill_context.get("ids", ())),
                        acceptance=[getattr(item, "line", lambda: str(item))() for item in acceptance_results],
                    ),
                )
                history.append({
                    "iteration": state.iteration,
                    "action": "verify_existing_result",
                    "model": state.selected_model,
                    "success": True,
                    "error": None,
                })
                return AgentLoopResult(state, tuple(history))
            carried_errors = tuple(dict.fromkeys(verification.errors + quality_errors + acceptance_errors))
            if carried_errors:
                state = state.transition(
                    AgentStatus.RETRYING,
                    errors=tuple(dict.fromkeys(state.errors + carried_errors)),
                )

        while not state.terminal:
            if state.iteration >= state.max_iterations:
                verification = self.verifier.verify(state.files_modified, state.tests_run)
                acceptance_ok, acceptance_errors, acceptance_results = self._acceptance(state)
                quality_errors = self.verifier.verify_task_deliverable(
                    task,
                    state.files_modified,
                    tuple(self.skill_context.get("ids", ())),
                )
                if state.files_modified and verification.passed and not quality_errors and acceptance_ok:
                    state = state.transition(
                        AgentStatus.COMPLETED,
                        final_confidence=verification.report.confidence,
                        metadata=self._metadata(
                            state,
                            verification=verification.report.to_dict(),
                            completion_reason="verified_at_iteration_boundary",
                            active_skills=list(self.skill_context.get("ids", ())),
                            acceptance=[getattr(item, "line", lambda: str(item))() for item in acceptance_results],
                        ),
                    )
                else:
                    boundary_errors = tuple(error for error in dict.fromkeys(
                        state.errors + verification.errors + quality_errors + acceptance_errors
                    ) if error != "iteration budget exhausted") + ("iteration budget exhausted",)
                    state = state.transition(
                        AgentStatus.BLOCKED,
                        errors=boundary_errors,
                        metadata=self._metadata(state, failure_kind=FailureKind.BUDGET.value),
                    )
                break

            state = state.next_iteration().transition(AgentStatus.PLANNING)
            progress_paths = tuple(dict.fromkeys(state.files_modified + state.files_read))
            context_task = task
            if progress_paths:
                context_task += "\nContinue from the existing progress in: " + ", ".join(progress_paths)
            context = self.context_engine.resolve(context_task, repo_map)

            try:
                action = self.planner.next_action(
                    task,
                    self._state_summary(state, self.skill_context),
                    context,
                    available,
                )
            except Exception as exc:
                message = str(exc)
                kind = classify_failure(message)
                history.append({
                    "iteration": state.iteration,
                    "action": "plan",
                    "model": state.selected_model,
                    "success": False,
                    "error": message,
                    "failure_kind": kind.value,
                })
                acceptance_ok, acceptance_errors, acceptance_results = self._acceptance(state)
                verification = self.verifier.verify(state.files_modified, state.tests_run)
                quality_errors = self.verifier.verify_task_deliverable(
                    task, state.files_modified, tuple(self.skill_context.get("ids", ())),
                )
                if (kind == FailureKind.TECHNICAL and state.files_modified and acceptance_ok
                        and verification.passed and not quality_errors):
                    state = state.transition(
                        AgentStatus.COMPLETED,
                        final_confidence=verification.report.confidence,
                        metadata=self._metadata(
                            state,
                            verification=verification.report.to_dict(),
                            completion_reason="acceptance_verified_after_provider_error",
                            previous_attempt_error=message,
                            acceptance=[getattr(item, "line", lambda: str(item))() for item in acceptance_results],
                            active_skills=list(self.skill_context.get("ids", ())),
                        ),
                    )
                    self._report_progress(state)
                    break
                if kind == FailureKind.TECHNICAL:
                    state = state.transition(
                        AgentStatus.BLOCKED,
                        errors=tuple(dict.fromkeys(state.errors + verification.errors
                                                   + quality_errors + acceptance_errors + (message,))),
                        metadata=self._metadata(state, failure_kind=kind.value),
                    )
                else:
                    state = state.transition(
                        AgentStatus.FAILED,
                        errors=state.errors + (message,),
                        metadata=self._metadata(state, failure_kind=kind.value),
                    )
                self._report_progress(state)
                break

            state = state.transition(AgentStatus.ACTING, current_action=action)
            if self.skill_policy is not None:
                try:
                    self.skill_policy.check(action.type)
                except Exception as exc:
                    message = str(exc)
                    state = state.transition(
                        AgentStatus.BLOCKED,
                        errors=state.errors + (message,),
                        metadata=self._metadata(state, failure_kind=FailureKind.POLICY.value),
                    )
                    history.append({
                        "iteration": state.iteration, "action": action.type.value,
                        "target": action.target, "model": selected_model,
                        "success": False, "error": message,
                        "failure_kind": FailureKind.POLICY.value,
                    })
                    break
            completed_action_keys = tuple(
                state.metadata.get("completed_action_keys") or ()
            )
            action_key = action.idempotency_key
            duplicate_guarded_action = (
                action.type in IDEMPOTENT_GUARDED_ACTIONS
                and action_key in completed_action_keys
            )
            if duplicate_guarded_action:
                observation = ActionObservation(
                    True,
                    action,
                    output="already applied in this mission",
                    metadata={
                        "idempotency_key": action_key,
                        "idempotent_replay_skipped": True,
                    },
                )
            else:
                observation = self.executor.execute(action)
            observations = state.observations + (observation,)
            files_read = state.files_read
            files_modified = state.files_modified
            tests_run = state.tests_run

            if observation.success and action.type == ActionType.READ_FILE and action.target:
                files_read = tuple(dict.fromkeys(files_read + (action.target,)))
            if observation.success and action.type in (ActionType.CREATE_FILE, ActionType.PATCH_FILE) and action.target:
                files_modified = tuple(dict.fromkeys(files_modified + (action.target,)))
                repo_map = build_repo_map(self.root)
            if observation.success and action.type == ActionType.IMPORT_ASSET:
                files_modified = tuple(dict.fromkeys(files_modified + tuple(observation.metadata.get("files_modified", ()))))
                repo_map = build_repo_map(self.root)
            # A rejected validation is evidence of a failed action, not a test
            # that ran.  Persisting it here caused the final verifier to replay
            # invalid model-supplied targets and abort the whole mission.
            if observation.success and action.type == ActionType.RUN_TEST:
                modules = action.payload if isinstance(action.payload, (list, tuple)) else [str(action.payload)]
                tests_run += tuple(modules)

            progress_metadata = dict(state.metadata)
            if observation.success and action.type in IDEMPOTENT_GUARDED_ACTIONS:
                progress_metadata["completed_action_keys"] = list(dict.fromkeys(
                    completed_action_keys + (action_key,)
                ))[-256:]
            state = state.transition(
                AgentStatus.OBSERVING,
                observations=observations,
                files_read=files_read,
                files_modified=files_modified,
                tests_run=tests_run,
                metadata=progress_metadata,
            )
            history.append({
                "iteration": state.iteration,
                "action": action.type.value,
                "target": action.target,
                "model": selected_model,
                "success": observation.success,
                "error": observation.error,
                "idempotency_key": action_key,
                "idempotent_replay_skipped": duplicate_guarded_action,
            })

            self._report_progress(state)

            if not observation.success:
                state = state.transition(
                    AgentStatus.RETRYING,
                    errors=state.errors + (observation.error,),
                )
                self._report_progress(state)
                continue

            repeated_inspection = (
                action.type == ActionType.INSPECT_RESULT
                and bool(files_modified)
                and len(observations) >= 2
                and all(
                    item.success and item.action.type == ActionType.INSPECT_RESULT
                    for item in observations[-2:]
                )
            )

            if action.type == ActionType.FINISH or repeated_inspection:
                verification = self.verifier.verify(files_modified, tests_run)
                acceptance_ok, acceptance_errors, acceptance_results = self._acceptance(state)
                quality_errors = self.verifier.verify_task_deliverable(
                    task,
                    files_modified,
                    tuple(self.skill_context.get("ids", ())),
                )
                if verification.passed and not quality_errors and acceptance_ok:
                    state = state.transition(
                        AgentStatus.COMPLETED,
                        final_confidence=verification.report.confidence,
                        metadata=self._metadata(
                            state,
                            verification=verification.report.to_dict(),
                            completion_reason=(
                                "verified_repeated_inspection"
                                if repeated_inspection else "model_finish"
                            ),
                            active_skills=list(self.skill_context.get("ids", ())),
                            acceptance=[getattr(item, "line", lambda: str(item))() for item in acceptance_results],
                        ),
                    )
                    self._report_progress(state)
                else:
                    verification_errors = verification.errors + quality_errors + acceptance_errors
                    if not verification_errors:
                        verification_errors = (
                            "verification evidence insufficient: %s" % verification.report.status.value,
                        )
                    state = state.transition(
                        AgentStatus.RETRYING,
                        errors=state.errors + verification_errors,
                        metadata=self._metadata(
                            state,
                            verification=verification.report.to_dict(),
                            deliverable_quality_errors=list(quality_errors),
                        ),
                    )
                    self._report_progress(state)
            else:
                state = state.transition(AgentStatus.VERIFYING)
                verification = self.verifier.verify(files_modified, ())
                if not verification.passed:
                    state = state.transition(
                        AgentStatus.RETRYING,
                        errors=state.errors + verification.errors,
                    )
                self._report_progress(state)

        return AgentLoopResult(state, tuple(history))
