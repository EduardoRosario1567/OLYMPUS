from dataclasses import dataclass, replace
from typing import Any, Callable, Optional, Tuple
import inspect
from olympus.agent.loop import AgentLoop, AgentLoopResult
from olympus.agent.recovery import FailureKind
from olympus.agent.state import AgentStatus
from olympus.routing.interfaces import RoutingAdapter


def _route_provider(route_id: str) -> str:
    value = str(route_id or "")
    if "::" in value:
        return value.split("::", 1)[0]
    if value == "openrouter/openrouter/free":
        return "openrouter"
    return value.split("/", 1)[0]


def _provider_wide_failure(error: object) -> bool:
    text = str(error or "").lower()
    return any(token in text for token in (
        "free-models-per-day",
        "daily quota",
        "daily limit",
        "requests per day",
        "authentication_error",
        "invalid api key",
        "invalid_api_key",
        "unauthorized",
        "forbidden",
        "billing_error",
        "payment required",
        "tokens per minute",
        "output tokens per minute",
        "input tokens per minute",
        "service tier",
    ))

@dataclass(frozen=True)
class AttemptResult:
    model: str
    result: AgentLoopResult

@dataclass(frozen=True)
class ControlPlaneResult:
    attempts: Tuple[AttemptResult, ...]
    @property
    def final(self):
        if not self.attempts: raise RuntimeError('control plane has no attempts')
        return self.attempts[-1].result
    @property
    def final_model(self):
        if not self.attempts: raise RuntimeError('control plane has no attempts')
        return self.attempts[-1].model
    @property
    def models_attempted(self):
        return tuple(x.model for x in self.attempts)

class AgentControlPlane:
    """Own model selection/failover around one bounded AgentLoop attempt."""
    def __init__(self, root: str, router: RoutingAdapter, selector: Any,
                 planner_factory: Callable, loop_factory: Callable,
                 telemetry: Optional[Callable[[dict], None]] = None):
        self.root=root; self.router=router; self.selector=selector
        self.planner_factory=planner_factory; self.loop_factory=loop_factory
        self.telemetry=telemetry
    def _emit(self,event,**payload):
        if self.telemetry:
            data={'event':event}; data.update(payload); self.telemetry(data)
    def _provider_for(self, model):
        # Route metadata is authoritative. OmniRoute model IDs encode upstream
        # provider names, but execution still goes through one gateway. Logical
        # labels such as conding_free/ollama_local/ollama_cloud let failover
        # isolate those tiers without changing the wire route.
        registry=getattr(self.selector, 'registry', None)
        lookup=getattr(registry, 'obter', None)
        if lookup is not None:
            try:
                registered=lookup(model)
            except Exception:
                registered=None
            provider=getattr(registered, 'provedor', None) if registered is not None else None
            if provider:
                return str(provider)
        return _route_provider(model)
    def candidates(self,task):
        method=getattr(self.selector,'select_candidates',None)
        result=tuple(method(task)) if method else (self.selector.select(task),)
        if not result: raise RuntimeError('no eligible model candidates')
        return result
    def run_attempts(self,task,max_iterations=12,initial_state=None,previously_attempted=()):
        attempts=[]
        checkpoint=initial_state
        all_candidates=self.candidates(task)
        previous=set(previously_attempted or ())
        untried=tuple(model for model in all_candidates if model not in previous)
        # Prioritize untouched routes on resume, then retain previously used
        # routes that are still eligible as bounded fallback. History alone
        # must not strand recovery on one new route. Current selection remains
        # authoritative for capacity, compatibility and spending restrictions.
        retried=tuple(model for model in all_candidates if model in previous)
        candidates=untried + retried
        # The OpenRouter free route dynamically chooses an underlying model on
        # every request. When it is our only zero-cost candidate, retrying the
        # route is real model failover rather than repeating a fixed model.
        # Three bounded attempts prevent one transient timeout from reaching
        # the user while keeping execution finite.
        if candidates == ('openrouter/openrouter/free',):
            candidates = candidates * 3
        blocked_providers=set()
        used_iterations=0
        for index,model in enumerate(candidates,1):
            provider=self._provider_for(model)
            if provider in blocked_providers:
                continue
            self._emit('model_selected',model=model,attempt=index)
            planner=self.planner_factory(self.router,model)
            loop=self.loop_factory(self.root,planner)
            remaining_iterations=max(1,int(max_iterations)-used_iterations)
            # A technical provider failure must not leave the next model with
            # one or two iterations and then falsely look like a mission
            # budget failure. Reserve a bounded recovery floor for handoff.
            if checkpoint is not None:
                remaining_iterations = max(
                    remaining_iterations,
                    min(8, int(max_iterations)),
                )
            kwargs={'selected_model':model,'max_iterations':remaining_iterations}
            if checkpoint is not None and 'initial_state' in inspect.signature(loop.run).parameters:
                continuation_metadata=dict(checkpoint.metadata)
                continuation_metadata["next_model_iteration_budget"]=remaining_iterations
                checkpoint=replace(checkpoint,metadata=continuation_metadata)
                kwargs['initial_state']=checkpoint
                self._emit(
                    'model_resume',
                    model=model,
                    iteration=checkpoint.iteration,
                    files_modified=list(checkpoint.files_modified),
                    tests_run=list(checkpoint.tests_run),
                    files_read=list(checkpoint.files_read),
                    last_error=checkpoint.errors[-1] if checkpoint.errors else None,
                    remaining_iterations=remaining_iterations,
                )
            result=loop.run(task,**kwargs)
            attempts.append(AttemptResult(model,result))
            used_iterations += max(1,result.state.iteration)
            if result.state.status == AgentStatus.COMPLETED: break
            if result.failure_kind not in (FailureKind.TECHNICAL.value, FailureKind.BUDGET.value): break
            # A technical failure must be allowed to hand off even when the
            # failing provider consumed the nominal iteration budget. The next
            # independent route gets a bounded recovery floor below; otherwise
            # a timeout on the last iteration would silently disable failover.
            checkpoint=result.state
            error=result.state.errors[-1] if result.state.errors else 'technical failure'
            if _provider_wide_failure(error):
                blocked_providers.add(provider)
            next_model=None
            for candidate in candidates[index:]:
                if self._provider_for(candidate) not in blocked_providers:
                    next_model=candidate
                    break
            self._emit(
                'model_failover',
                model=model,
                next_model=next_model,
                from_provider=provider,
                to_provider=self._provider_for(next_model) if next_model else None,
                cross_provider=bool(next_model and self._provider_for(next_model) != provider),
                provider_blocked=provider in blocked_providers,
                error=error,
                dynamic_route_retry=(
                    next_model == model == 'openrouter/openrouter/free'
                ),
            )
        return ControlPlaneResult(tuple(attempts))
