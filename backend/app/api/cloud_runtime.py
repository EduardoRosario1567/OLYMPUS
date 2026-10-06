from olympus.cloud.project_studio import PreviewStopError
import os
from pathlib import Path
import json
import shutil
import time
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from olympus.agent.autonomous_developer import AutonomousDeveloper
from olympus.memory import build_memory_store
from olympus.agent.mission_checkpoint import MissionCheckpointStore
from olympus.skills import SkillRegistry
from olympus.cloud.runtime import CloudRuntime
from olympus.cloud.project_catalog import ProjectCatalogError
from olympus.cloud.attachments import ProjectAttachmentStore
from olympus.cloud.project_preview import ProjectPreviewSessions
from olympus.cloud.project_studio import ProjectFileEditor, ProjectRuntimeManager
from olympus.cloud.github_integration import GitHubIntegrationService
from olympus.cloud.deployment import DeploymentCoordinator, SQLiteDeploymentRecordStore
from olympus.cloud.secret_vault import configured_secret_vault
from olympus.cloud.railway_provider import RailwayIntegrationService, RailwayProvider, SQLiteRailwayDeploymentBindingStore
from app.core.deps import identidade_com_permissao
from app.core.provider_runtime import build_mission_routing, build_visual_review_routing, build_delivery_verifier, routing_policy
from app.core.saas import PLATFORM
from olympus.saas.platform import EntitlementError

router = APIRouter(prefix="/cloud", tags=["cloud-runtime"])
_can_read = identidade_com_permissao("projects.read")
_can_run = identidade_com_permissao("missions.run")


class CloudMissionCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=3, max_length=12000)
    max_iterations: int = Field(default=24, ge=1, le=24)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    routing_mode: str = Field(default="free_first", pattern="^(free_first|protected|premium_direct)$")
    paid_fallback_authorized: bool = False
    paid_spend_cap_usd: float = Field(default=0.0, ge=0, le=1000)
    free_attempt_limit: Optional[int] = Field(default=None, ge=1, le=8)
    paid_attempt_limit: int = Field(default=1, ge=1, le=3)


class CloudExecutionAction(BaseModel):
    execution_id: str


class CloudProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)




def _adaptive_model_timeout(task: str) -> int:
    """Choose a bounded inference timeout from the human task shape.

    Free large coding models routinely need more than 30 seconds for web/app
    actions. Small deterministic/file tasks keep a shorter ceiling so a dead
    route still fails over promptly.
    """
    text = str(task or "").lower()
    if any(token in text for token in (
        "landing page", "website", "site", "página", "pagina", "frontend",
        "aplicativo", "application", " app ", "jogo", "game", "dashboard",
    )):
        return 90
    if any(token in text for token in (
        "código", "codigo", "code", "bug", "corrija", "fix", "refactor",
        "api", "backend", "python", "typescript", "javascript",
    )):
        return 60
    if any(token in text for token in (
        "arquivo", "file", "calcule", "calculate", "resuma", "summarize",
    )):
        return 45
    return 60


def _quality_verifier(workspace: str):
    return build_delivery_verifier(workspace,routing_factory=build_visual_review_routing)


def _runner_factory(workspace: str, telemetry):
    from olympus.skills.fabric import SkillsFabric
    policy_path = Path(workspace) / ".olympus" / "execution-policy.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        policy = None
    fabric_tenant = (policy or {}).get("skills_fabric_tenant", "local")
    runtime = globals().get("_RUNTIME")
    record = runtime.get(Path(workspace).name) if runtime is not None else None
    if record is not None and record.workspace and Path(record.workspace).resolve() == Path(workspace).resolve():
        # Also resolves pre-3.0.8 checkpoints and takes identity from the
        # trusted execution store rather than a workspace-editable policy.
        fabric_tenant = record.tenant_id
    default_timeout = int(os.environ.get("OLYMPUS_MODEL_TIMEOUT", "90"))
    try:
        mission_timeout = int((policy or {}).get("model_timeout_seconds", default_timeout))
    except (TypeError, ValueError):
        mission_timeout = default_timeout
    mission_timeout = max(20, min(180, mission_timeout))
    router_adapter, selector = build_mission_routing(
        mission_timeout,
        policy_override=policy,
    )
    return AutonomousDeveloper(
        root=workspace,
        router=router_adapter,
        selector=selector,
        telemetry=telemetry,
        checkpoint_store=MissionCheckpointStore(workspace),
        skills_fabric=SkillsFabric(tenant_id=fabric_tenant),
        verifier_factory=_quality_verifier,
        skill_registry=SkillRegistry((
            os.environ.get(
                "OLYMPUS_SKILLS_DIR",
                str(Path(__file__).resolve().parents[3] / ".olympus" / "skills"),
            ),
        )),
    )


_RUNTIME = CloudRuntime(
    os.environ.get("OLYMPUS_CLOUD_DATA_DIR", ".olympus/cloud"),
    _runner_factory,
    verifier_factory=_quality_verifier,
    max_workers=int(os.environ.get("OLYMPUS_CLOUD_WORKERS", "2")),
    memory_store=build_memory_store(
        os.environ.get("OLYMPUS_MEMORY_DATABASE_URL")
        or os.environ.get("OLYMPUS_MEMORY_DB", str(Path(__file__).resolve().parents[3] / "olympus_memory.db"))
    ),
)
_ATTACHMENTS = ProjectAttachmentStore(_RUNTIME.projects)
_PREVIEWS = ProjectPreviewSessions(_RUNTIME.projects)
_FILES = ProjectFileEditor(_RUNTIME.projects, _RUNTIME.versions)
_STUDIO_RUNTIMES = ProjectRuntimeManager(_RUNTIME.projects)
_GITHUB = GitHubIntegrationService(_RUNTIME.projects, _RUNTIME.data_dir / "integrations")
_RAILWAY = RailwayIntegrationService(_RUNTIME.data_dir / "integrations")
_DEPLOYMENT_SECRETS = configured_secret_vault(
    _RUNTIME.data_dir / "integrations",
    os.environ.get("OLYMPUS_KMS_PROVIDER", ""),
)
_RAILWAY_DEPLOYMENT_BINDINGS = SQLiteRailwayDeploymentBindingStore(_RUNTIME.data_dir / "integrations" / "railway-deployments.sqlite3")
_RAILWAY_PROVIDER = RailwayProvider(_RAILWAY.bindings, _RAILWAY.token, deployment_store=_RAILWAY_DEPLOYMENT_BINDINGS)
_DEPLOYMENT_RECORDS = SQLiteDeploymentRecordStore(_RUNTIME.data_dir / "integrations" / "deployments.sqlite3")
_DEPLOYMENTS = DeploymentCoordinator(_DEPLOYMENT_SECRETS, (_RAILWAY_PROVIDER,), record_store=_DEPLOYMENT_RECORDS)


_CONTINUATION_TOKENS = frozenset({
    "segue", "seguir", "continue", "continuar", "continua",
    "retomar", "retome", "prosseguir", "prossiga", "vamos seguir",
})

def _normalized_control_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().rstrip(".!?").split())

def _is_continuation_task(value: str) -> bool:
    return _normalized_control_text(value) in _CONTINUATION_TOKENS

def _latest_meaningful_resumable(project_id: str, tenant_id: str):
    resumable = {"paused_capacity", "cancelled", "blocked", "failed"}
    for item in _RUNTIME.list(tenant_id, 50, project_id=project_id):
        if item.status in resumable and not _is_continuation_task(item.task):
            return item
    return None


def _github_publish_hook(execution, version):
    binding = _GITHUB.bindings.get(execution.project_id, execution.tenant_id)
    if binding is not None and binding.auto_sync and _GITHUB.account(execution.tenant_id) is None:
        raise PermissionError(
            "A publicação GitHub foi solicitada, mas a sessão/token do GitHub não está conectado."
        )
    return _GITHUB.auto_sync(
        execution.project_id,
        execution.tenant_id,
        "Olympus: %s" % str(execution.task).strip()[:160],
    )


_github_publish_hook.required = True


_RUNTIME.add_publish_hook(_github_publish_hook)


def _view(record):
    if record is None:
        raise HTTPException(status_code=404, detail="execution not found")
    return {
        "execution_id": record.execution_id,
        "project_id": record.project_id,
        "mission_id": record.mission_id,
        "task": record.task,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "workspace": None,
        "error": record.error,
        "resume_count": record.resume_count,
    }


@router.post("/missions", status_code=202)
def submit(payload: CloudMissionCreate, identity=Depends(_can_run)):
    # Short conversational controls such as "segue" mean resume the latest
    # meaningful paused mission in this project. They are not new coding tasks.
    if _is_continuation_task(payload.task):
        previous = _latest_meaningful_resumable(payload.project_id, identity.tenant_id)
        if previous is None:
            raise HTTPException(status_code=409, detail="Não há missão pausada para continuar neste projeto.")
        resumed = _RUNTIME.resume(previous.execution_id)
        return _view(resumed)
    reserved = False
    try:
        PLATFORM.consume(identity.tenant_id, identity.user_id, "missions_month")
        reserved = True
        PLATFORM.record_action(identity.tenant_id, identity.user_id, "mission.requested", "project", payload.project_id, {})
        _STUDIO_RUNTIMES.stop_checked(payload.project_id, identity.tenant_id)
        task = _ATTACHMENTS.augment_task(payload.project_id, payload.task, payload.attachment_ids, tenant_id=identity.tenant_id)
        if payload.paid_fallback_authorized and payload.paid_spend_cap_usd <= 0:
            raise ValueError("Defina um limite de gasto para autorizar a continuação paga.")
        if payload.routing_mode == "premium_direct" and not payload.paid_fallback_authorized:
            raise ValueError("A rota premium direta exige autorização explícita.")
        execution_policy = {
            "mode": payload.routing_mode,
            "paid_fallback_authorized": payload.paid_fallback_authorized,
            "paid_spend_cap_usd": payload.paid_spend_cap_usd,
            "paid_attempt_limit": payload.paid_attempt_limit,
        }
        if payload.free_attempt_limit is not None:
            execution_policy["free_attempt_limit"] = payload.free_attempt_limit
        execution_policy = asdict(routing_policy(execution_policy))
        execution_policy["model_timeout_seconds"] = _adaptive_model_timeout(task)
        execution_policy["skills_fabric_tenant"] = identity.tenant_id
        result = _RUNTIME.submit(
            payload.project_id,
            task,
            payload.max_iterations,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            execution_policy=execution_policy,
        )
        return _view(result)
    except EntitlementError as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    except ValueError as exc:
        if reserved:
            PLATFORM.refund(identity.tenant_id, identity.user_id, "missions_month")
        raise HTTPException(status_code=400, detail=str(exc))
    except PreviewStopError as exc:
        if reserved:
            PLATFORM.refund(identity.tenant_id, identity.user_id, "missions_month")
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError:
        if reserved:
            PLATFORM.refund(identity.tenant_id, identity.user_id, "missions_month")
        raise HTTPException(status_code=409, detail="Este projeto já possui uma missão em andamento.")
    except PermissionError:
        if reserved:
            PLATFORM.refund(identity.tenant_id, identity.user_id, "missions_month")
        raise HTTPException(status_code=404, detail="project not found")
    except Exception:
        if reserved:
            PLATFORM.refund(identity.tenant_id, identity.user_id, "missions_month")
        raise


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str, identity=Depends(_can_read)):
    record = _RUNTIME.get(execution_id)
    if record is None or record.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="execution not found")
    return _view(record)


@router.get("/executions")
def list_executions(
    limit: int = Query(default=100, ge=1, le=500),
    project_id: Optional[str] = Query(default=None, max_length=128),
    status: Optional[str] = Query(default=None, max_length=40),
    identity=Depends(_can_read),
):
    return {"executions": [_view(item) for item in _RUNTIME.list(identity.tenant_id, limit, project_id, status)]}


@router.get("/executions/{execution_id}/events")
def get_events(execution_id: str, after: int = 0, identity=Depends(_can_read)):
    record = _RUNTIME.get(execution_id)
    if record is None or record.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="execution not found")
    return {"execution_id": execution_id, "events": _RUNTIME.events(execution_id, after)}


@router.post("/executions/{execution_id}/cancel")
def cancel(execution_id: str, identity=Depends(_can_run)):
    record = _RUNTIME.get(execution_id)
    if record is None or record.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="execution not found")
    if not _RUNTIME.cancel(execution_id):
        raise HTTPException(status_code=409, detail="execution cannot be cancelled")
    return _view(_RUNTIME.get(execution_id))


@router.post("/executions/{execution_id}/resume")
def resume(execution_id: str, identity=Depends(_can_run)):
    record = _RUNTIME.get(execution_id)
    if record is None or record.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="execution not found")
    return _view(_RUNTIME.resume(execution_id))


@router.get("/health")
def health():
    return {"status": "ok", "runtime": "persistent-async"}

class DecisionCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    options: list
    context: dict = {}
    ttl_seconds: Optional[float] = None


class DecisionAnswer(BaseModel):
    choice: object
    comment: Optional[str] = None


@router.post("/executions/{execution_id}/decisions", status_code=201)
def request_decision(execution_id: str, payload: DecisionCreate, identity=Depends(_can_run)):
    record = _RUNTIME.get(execution_id)
    if record is None or record.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="execution not found")
    try:
        req = _RUNTIME.request_decision(execution_id, payload.question, payload.options, payload.context, payload.ttl_seconds)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"decision_id": req.decision_id, "execution_id": req.execution_id, "status": req.status,
            "question": req.question, "options": req.options, "expires_at": req.expires_at}


@router.post("/executions/{execution_id}/decisions/{decision_id}")
def answer_decision(execution_id: str, decision_id: str, payload: DecisionAnswer, identity=Depends(_can_run)):
    try:
        req = _RUNTIME.answer_decision(execution_id, decision_id, identity.tenant_id, payload.choice, payload.comment)
    except KeyError:
        raise HTTPException(status_code=404, detail="decision not found")
    except TimeoutError:
        raise HTTPException(status_code=409, detail="decision expired")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"decision_id": req.decision_id, "execution_id": req.execution_id, "status": req.status,
            "answered_at": req.answered_at}


def _find_project_workspace(project_id: str, tenant_id: str) -> Optional[Path]:
    # Resolve the registered, tenant-owned workspace; never search other tenants.
    source = _RUNTIME.projects.project_root(project_id, tenant_id=tenant_id)
    return source if source.is_dir() else None


def _archive_project_workspace(project_id: str, tenant_id: str) -> tuple[Optional[Path], Optional[Path]]:
    source = _find_project_workspace(project_id, tenant_id)
    if source is None:
        return None, None
    trash = Path(_RUNTIME.data_dir) / "project-trash"
    trash.mkdir(parents=True, exist_ok=True)
    target = trash / (time.strftime("%Y%m%d_%H%M%S") + "-" + project_id)
    suffix = 1
    while target.exists():
        target = trash / (time.strftime("%Y%m%d_%H%M%S") + "-" + project_id + "-" + str(suffix))
        suffix += 1
    shutil.move(str(source), str(target))
    return source, target


@router.patch("/projects/{project_id}")
def rename_cloud_project(project_id: str, payload: CloudProjectUpdate, identity=Depends(_can_run)):
    try:
        updated = _RUNTIME.projects.rename(project_id, identity.tenant_id, payload.name)
    except ProjectCatalogError as exc:
        detail = str(exc)
        status = 404 if "não encontrado" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)
    PLATFORM.record_action(identity.tenant_id, identity.user_id, "project.renamed", "project", project_id, {"name": updated.get("name")})
    return updated


@router.delete("/projects/{project_id}", status_code=204)
def delete_cloud_project(project_id: str, identity=Depends(_can_run)):
    # Ownership is checked before busy checks, runtime stop or filesystem work.
    project = _RUNTIME.projects.get(project_id)
    if project is None or project.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    if _RUNTIME.project_is_busy(project_id, identity.tenant_id):
        raise HTTPException(status_code=409, detail="O projeto possui uma missão em andamento. Cancele ou aguarde a conclusão antes de excluir.")
    try:
        _STUDIO_RUNTIMES.stop_checked(project_id, identity.tenant_id)
    except PreviewStopError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    source = archived = None
    try:
        source, archived = _archive_project_workspace(project_id, identity.tenant_id)
        removed = _RUNTIME.projects.remove(project_id, identity.tenant_id)
    except ProjectCatalogError as exc:
        if source is not None and archived is not None and archived.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archived), str(source))
        detail = str(exc)
        status = 404 if "não encontrado" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)
    except Exception:
        if source is not None and archived is not None and archived.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archived), str(source))
        raise
    PLATFORM.record_action(identity.tenant_id, identity.user_id, "project.deleted", "project", project_id, {"name": removed.get("name"), "recoverable": bool(archived)})
    return None
