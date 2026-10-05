import os
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from olympus.agent.action_normalizer import normalize_action_text
from olympus.agent.actions import ActionType
from olympus.routing.capacity_fabric import CapacityFabric, capacity_fabric_snapshot
from olympus.routing.provider_fabric import provider_route_id

from app.core.deps import identidade_com_permissao
from app.core.provider_runtime import (
    _rank_live_models,
    build_provider_registry,
    provider_catalog,
    remove_provider_secret,
    remove_provider_credentials,
    update_provider_secret,
    update_provider_credentials,
    update_routing_policy,
    update_provider_preference,
)

router = APIRouter(prefix="/providers", tags=["providers"])
_can_read = identidade_com_permissao("projects.read")
_can_manage = identidade_com_permissao("members.manage")


class ProviderPreferenceUpdate(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=1, le=999)
    automatic: Optional[bool] = None


class RoutingPolicyUpdate(BaseModel):
    mode: str = Field(default="free_first", pattern="^(free_first|protected|premium_direct)$")
    free_attempt_limit: int = Field(default=6, ge=1, le=8)
    paid_fallback_authorized: bool = False
    paid_attempt_limit: int = Field(default=1, ge=1, le=3)
    paid_spend_cap_usd: float = Field(default=0.0, ge=0, le=1000)


class ProviderCredentialUpdate(BaseModel):
    secret: str = Field(min_length=1, max_length=4096)


class ProviderCredentialsUpdate(BaseModel):
    values: Dict[str, str] = Field(default_factory=dict)


class ProviderQualificationRequest(BaseModel):
    model_id: Optional[str] = Field(default=None, max_length=512)
    max_models: int = Field(default=3, ge=1, le=5)
    allow_metered: bool = False


@router.get("/catalog")
def catalog(_identity=Depends(_can_read)):
    return provider_catalog()


@router.put("/routing-policy")
def save_routing_policy(payload: RoutingPolicyUpdate, _identity=Depends(_can_manage)):
    try:
        update_routing_policy(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return provider_catalog()


@router.patch("/{provider_id}")
def update_provider(provider_id: str, payload: ProviderPreferenceUpdate, _identity=Depends(_can_manage)):
    if payload.enabled is None and payload.priority is None and payload.automatic is None:
        raise HTTPException(status_code=400, detail="Informe a ativação ou a prioridade.")
    try:
        update_provider_preference(
            provider_id,
            enabled=payload.enabled,
            priority=payload.priority,
            automatic=payload.automatic,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Provedor não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return provider_catalog()


@router.put("/{provider_id}/credential")
def save_provider_credential(provider_id: str, payload: ProviderCredentialUpdate, _identity=Depends(_can_manage)):
    try:
        update_provider_secret(provider_id, payload.secret)
    except KeyError:
        raise HTTPException(status_code=404, detail="Provedor não encontrado ou sem credencial configurável.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return provider_catalog()


@router.delete("/{provider_id}/credential", status_code=204)
def delete_provider_credential(provider_id: str, _identity=Depends(_can_manage)):
    try:
        remove_provider_secret(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Provedor não encontrado ou sem credencial configurável.")


@router.put("/{provider_id}/credentials")
def save_provider_credentials(provider_id: str, payload: ProviderCredentialsUpdate, _identity=Depends(_can_manage)):
    try:
        update_provider_credentials(provider_id, payload.values)
    except KeyError:
        raise HTTPException(status_code=404, detail="Provedor não encontrado ou sem credenciais configuráveis.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return provider_catalog()


@router.delete("/{provider_id}/credentials", status_code=204)
def delete_provider_credentials(provider_id: str, _identity=Depends(_can_manage)):
    try:
        remove_provider_credentials(provider_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Provedor não encontrado ou sem credenciais configuráveis.")


@router.post("/{provider_id}/test")
def test_provider(provider_id: str, _identity=Depends(_can_read)):
    try:
        test_timeout = float(os.environ.get("OLYMPUS_PROVIDER_TEST_TIMEOUT", "60"))
    except (TypeError, ValueError):
        test_timeout = 60.0
    test_timeout = max(10.0, min(180.0, test_timeout))
    registry = build_provider_registry(timeout_seconds=test_timeout)
    if provider_id not in registry.ids():
        raise HTTPException(status_code=404, detail="Provedor não encontrado.")
    health = registry.adapter(provider_id).health()
    model_count = 0
    models = ()
    if health.healthy:
        try:
            models = tuple(
                item.model_id for item in registry.adapter(provider_id).list_models()
                if item.available
            )
            model_count = len(models)
        except Exception:
            model_count = 0
    inference_ready = False
    tested_model = None
    inference_error = None
    if health.healthy and models:
        if provider_id == "fcc":
            from app.core.provider_runtime import _fcc_free_models
            candidates = _rank_live_models(_fcc_free_models(models))[:3]
        else:
            candidates = (
            ("openrouter/openrouter/free",)
            if provider_id == "omniroute" and "openrouter/openrouter/free" in models
            else _rank_live_models(models)[:3]
            )
        if provider_id == "fcc" and not candidates:
            inference_error = "Nenhum modelo gratuito ou local foi identificado com segurança no catálogo FCC."
        for model_id in candidates:
            result = registry.adapter(provider_id).execute(
                model_id,
                'Return only {"type":"finish","target":null,"payload":null,"reason":"connection test"}',
                max_tokens=256,
                temperature=0.0,
            )
            tested_model = model_id
            if result.success and str(result.output or "").strip():
                try:
                    action = normalize_action_text(str(result.output))
                except Exception as exc:
                    inference_error = "action_protocol_invalid: %s" % exc
                    continue
                if action.type == ActionType.FINISH and action.target is None:
                    inference_ready = True
                    inference_error = None
                    break
                inference_error = (
                    "action_protocol_invalid: expected finish without target, got %s"
                    % action.type.value
                )
                continue
            inference_error = str(result.error or result.status or "inference unavailable")
    return {
        "id": provider_id,
        "connected": bool(health.healthy),
        "inference_ready": inference_ready,
        "healthy": inference_ready,
        "status": "inference_ready" if inference_ready else "connected_only" if health.healthy else health.status,
        "model_count": model_count,
        "model": tested_model,
        "error": inference_error,
        "message": (
            "Protocolo Olympus confirmado. Este provedor pode participar do fallback."
            if inference_ready else
            "Conta conectada, mas a geração não está disponível nesta rota."
            if health.healthy else
            "A conexão ainda não está disponível."
        ),
    }

@router.get("/capacity")
def capacity_status(_identity=Depends(_can_read)):
    return capacity_fabric_snapshot()


@router.post("/{provider_id}/qualify")
def qualify_provider(provider_id: str, payload: ProviderQualificationRequest, _identity=Depends(_can_manage)):
    """Run bounded, real protocol probes before a model joins trusted routing.

    This first Capacity Fabric qualification level validates connectivity,
    structured finish actions and structured create_file actions. It does not
    claim that repository tool execution has been proven; that is a later E2E
    qualification level.
    """
    from app.core.provider_runtime import _PROVIDER_TIERS

    provider_id = str(provider_id or "").strip().lower()
    registry = build_provider_registry(timeout_seconds=max(20.0, min(120.0, float(os.environ.get("OLYMPUS_QUALIFICATION_TIMEOUT", "60")))))
    if provider_id not in registry.ids():
        raise HTTPException(status_code=404, detail="Provedor não encontrado.")
    tier = _PROVIDER_TIERS.get(provider_id, "paid")
    if tier in {"paid", "free_paid"} and not payload.allow_metered:
        raise HTTPException(status_code=409, detail="Este provedor pode consumir créditos. Confirme a qualificação com allow_metered=true.")

    adapter = registry.adapter(provider_id)
    health = adapter.health()
    if not health.healthy:
        raise HTTPException(status_code=409, detail="Provedor sem saúde suficiente para qualificação: %s" % (health.status or "unavailable"))
    try:
        live_models = tuple(item.model_id for item in adapter.list_models() if item.available and item.model_id)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Não foi possível descobrir modelos: %s" % exc)
    if payload.model_id:
        candidates = (payload.model_id,) if payload.model_id in set(live_models) else ()
    elif provider_id == "fcc":
        from app.core.provider_runtime import _fcc_free_models
        candidates = _rank_live_models(_fcc_free_models(live_models))[:payload.max_models]
    else:
        candidates = _rank_live_models(live_models)[:payload.max_models]
    if not candidates:
        raise HTTPException(status_code=409, detail="Nenhum modelo elegível foi encontrado para qualificação.")

    fabric = CapacityFabric()
    reports = []
    for model_id in candidates:
        route_id = model_id if provider_id == "omniroute" else provider_route_id(provider_id, model_id)
        probe_rows = []
        qualified = True
        probes = (
            (
                "response",
                'Return only {"type":"finish","target":null,"payload":null,"reason":"OLYMPUS_PROBE_OK"}',
                lambda action: action.type == ActionType.FINISH and action.target is None,
            ),
            (
                "action_protocol",
                'Return only {"type":"finish","target":null,"payload":null,"reason":"structured action protocol ok"}',
                lambda action: action.type == ActionType.FINISH and action.target is None,
            ),
            (
                "code_action",
                'Return only {"type":"create_file","target":"qualification_probe.txt","payload":"OLYMPUS_PROBE_OK","reason":"qualification"}',
                lambda action: action.type == ActionType.CREATE_FILE and action.target == "qualification_probe.txt" and str(action.payload) == "OLYMPUS_PROBE_OK",
            ),
        )
        for probe_name, prompt, validator in probes:
            result = adapter.execute(model_id, prompt, max_tokens=512, temperature=0.0)
            fabric.observe(route_id, result, provider_hint=provider_id)
            ok = False
            error = str(result.error or "")
            if result.success and str(result.output or "").strip():
                try:
                    action = normalize_action_text(str(result.output))
                    ok = bool(validator(action))
                    if not ok:
                        error = "action_protocol_mismatch"
                except Exception as exc:
                    error = "action_protocol_invalid: %s" % exc
            fabric.record_probe(provider_id, route_id, probe_name, ok, latency_ms=result.latency_ms, error=error)
            probe_rows.append({"probe": probe_name, "ok": ok, "latency_ms": result.latency_ms, "error": error or None})
            if not ok:
                qualified = False
                break
        reports.append({"provider": provider_id, "model": model_id, "route_id": route_id, "qualified": qualified, "probes": probe_rows})

    return {
        "provider": provider_id,
        "qualification_level": "agent_action_v1",
        "models": reports,
        "qualified_count": sum(1 for row in reports if row["qualified"]),
        "capacity": capacity_fabric_snapshot(),
    }


@router.post("/{provider_id}/capacity/reset")
def reset_provider_capacity(provider_id: str, _identity=Depends(_can_manage)):
    return CapacityFabric().reset(provider=provider_id)


@router.get("/health")
def provider_health(_identity=Depends(_can_read)):
    rows = []
    for health in build_provider_registry().health_all():
        rows.append({"id": health.provider, "healthy": bool(health.healthy), "status": health.status,
                     "metadata": health.metadata})
    return {"providers": rows}


@router.get("")
def providers(_identity=Depends(_can_read)):
    registry = build_provider_registry()
    return {"providers": [{"id": pid, "healthy": pid in registry.healthy_ids()} for pid in registry.ids()]}


@router.get("/models/ranked")
def ranked_models(_identity=Depends(_can_read)):
    registry = build_provider_registry()
    models = []
    for provider_id in registry.healthy_ids():
        try:
            for model in registry.adapter(provider_id).list_models():
                models.append({"provider": provider_id, "model": model.model_id, "available": model.available})
        except Exception:
            pass
    return {"models": models}

# Model Lab ranking endpoint. Runtime observations can be injected by the
# application service; a fresh lab yields capability/health-weighted priors.
@router.get("/models/lab")
def model_lab_rankings(category: str = "action_protocol", _identity=Depends(_can_read)):
    from olympus.routing.model_lab import BenchmarkCategory, ModelLab
    try:
        benchmark = BenchmarkCategory(category)
    except ValueError:
        benchmark = BenchmarkCategory.ACTION_PROTOCOL
    registry = build_provider_registry()
    lab = ModelLab()
    routes = []
    for provider_id in registry.healthy_ids():
        try:
            for model in registry.adapter(provider_id).list_models():
                routes.append({
                    "provider": provider_id,
                    "model": model.model_id,
                    "capability_score": 0.5,
                    "health_score": 1.0,
                    "cost_score": 1.0,
                })
        except Exception:
            pass
    return {"category": benchmark.value, "models": list(lab.rank(benchmark, routes))}
