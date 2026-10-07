"""Single provider fabric used by health endpoints and cloud missions.

The public catalog deliberately exposes configuration state, never credential
values.  Provider preferences live outside the source tree and can therefore
be changed by the local control center without rewriting ``backend/.env``.
"""
import json
import time
import os
from pathlib import Path
import tempfile
import threading
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Tuple

from olympus.agent.model_selector import OlympusModelSelector
from olympus.agent.multibrain_registry import AgentModelRoute, FREE_ROUTER_MODEL_ID
from olympus.routing.omniroute_adapter import OmniRouteAdapter
from olympus.routing.interfaces import RoutingHealth
from olympus.routing.interfaces import RoutingExecutionResult
from olympus.routing.capacity_fabric import (
    CapacityAwareRoutingAdapter,
    CapacityFabric,
    capacity_filter_routes,
    capacity_fabric_snapshot,
)
from olympus.routing.provider_fabric import (
    MultiProviderRoutingAdapter,
    OpenAICompatibleAdapter,
    CloudflareWorkersAIAdapter,
    GeminiNativeAdapter,
    ProviderConfig,
    ProviderRegistry,
    provider_route_id,
    split_provider_route,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SETTINGS_LOCK = threading.RLock()

_DIRECT_PROVIDERS = (
    ("fcc", "Free Claude Code", "OLYMPUS_FCC_URL", "http://127.0.0.1:8082/v1", "FCC_PROXY_TOKEN", 15, "Gateway gratuito e local"),
    ("openrouter", "OpenRouter", "OLYMPUS_OPENROUTER_URL", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", 20, "Nuvem"),
    ("groq", "Groq", "OLYMPUS_GROQ_URL", "https://api.groq.com/openai/v1", "GROQ_API_KEY", 30, "Gratuito"),
    ("cerebras", "Cerebras", "OLYMPUS_CEREBRAS_URL", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", 40, "Requer ativação e pode exigir cartão/créditos"),
    ("ollama", "Ollama local", "OLYMPUS_OLLAMA_URL", "http://127.0.0.1:11434/v1", None, 50, "Local"),
    ("ollama_cloud", "Ollama Cloud", "OLYMPUS_OLLAMA_CLOUD_URL", "https://ollama.com/v1", "OLLAMA_API_KEY", 55, "Conforme plano"),
    ("openai", "OpenAI", "OLYMPUS_OPENAI_URL", "https://api.openai.com/v1", "OPENAI_API_KEY", 60, "Pago"),
    ("gemini", "Google Gemini", "OLYMPUS_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY", 70, "Conforme plano"),
    ("mistral", "Mistral AI", "OLYMPUS_MISTRAL_URL", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", 80, "Conforme plano"),
    ("zai", "Z.AI", "OLYMPUS_ZAI_URL", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", 90, "Gratuito e pago"),
    ("cloudflare", "Cloudflare Workers AI", "OLYMPUS_CLOUDFLARE_URL", "", "CLOUDFLARE_API_KEY", 100, "Franquia gratuita"),
    ("kimi", "Kimi", "OLYMPUS_KIMI_URL", "https://api.moonshot.ai/v1", "KIMI_API_KEY", 110, "Pago opcional"),
    ("opencode_zen", "OpenCode Zen", "OLYMPUS_OPENCODE_ZEN_URL", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY", 120, "Modelos gratuitos e pagos"),
    ("together", "Together AI", "OLYMPUS_TOGETHER_URL", "https://api.together.ai/v1", "TOGETHER_API_KEY", 130, "Conforme plano"),
    ("fireworks", "Fireworks AI", "OLYMPUS_FIREWORKS_URL", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", 140, "Conforme plano"),
)

_PROVIDER_TIERS = {
    "omniroute": "free", "fcc": "free", "openrouter": "free", "groq": "free",
    "cerebras": "free_paid", "ollama": "local", "ollama_cloud": "free_paid", "gemini": "free",
    "mistral": "free", "zai": "free", "cloudflare": "free",
    "openai": "paid", "kimi": "paid",
    "opencode_zen": "free_paid",
    "together": "free_paid", "fireworks": "free_paid",
}

_PROVIDER_LABELS = {"omniroute": "OmniRoute"}
_PROVIDER_LABELS.update({row[0]: row[1] for row in _DIRECT_PROVIDERS})
_PROVIDER_KEY_ENVS = {"opencode_zen": "OPENCODE_API_KEY", "omniroute": "OLYMPUS_OMNIROUTE_API_KEY", "ollama_cloud": "OLLAMA_API_KEY"}


_PROVIDER_CREDENTIAL_SCHEMAS = {
    "cloudflare": (
        {
            "id": "api_token",
            "env": "CLOUDFLARE_API_KEY",
            "label": "API Token",
            "secret": True,
            "required": True,
            "placeholder": "Cole o Workers AI API Token",
            "help": "Token com permissão Account > Workers AI > Read (ou Read/Edit durante homologação).",
            "max_length": 4096,
        },
        {
            "id": "account_id",
            "env": "CLOUDFLARE_ACCOUNT_ID",
            "label": "Account ID",
            "secret": False,
            "required": True,
            "placeholder": "Cole o Account ID da Cloudflare",
            "help": "Identificador da conta usado para construir o endpoint /accounts/{account_id}/ai/v1.",
            "max_length": 256,
            "pattern": r"^[A-Za-z0-9_-]{6,256}$",
        },
    ),
}


def _provider_credential_schema(provider_id: str):
    provider = str(provider_id or "").strip().lower()
    if provider in _LOCAL_PROVIDER_IDS:
        return ()
    if provider in _PROVIDER_CREDENTIAL_SCHEMAS:
        return _PROVIDER_CREDENTIAL_SCHEMAS[provider]
    if provider not in _PROVIDER_LABELS:
        return ()
    return ({
        "id": "api_key",
        "env": _provider_key_env(provider),
        "label": "API Key",
        "secret": True,
        "required": True,
        "placeholder": "Cole a chave aqui",
        "help": "A chave fica armazenada localmente no backend/.env e nunca volta no catálogo.",
        "max_length": 4096,
    },)


def provider_credential_fields(provider_id: str):
    """Public credential field metadata, never credential values."""
    rows = []
    for field in _provider_credential_schema(provider_id):
        rows.append({
            "id": field["id"],
            "label": field["label"],
            "secret": bool(field.get("secret", True)),
            "required": bool(field.get("required", True)),
            "configured": bool(os.environ.get(field["env"], "").strip()),
            "placeholder": field.get("placeholder", ""),
            "help": field.get("help", ""),
        })
    return rows


def _provider_credentials_configured(provider_id: str) -> bool:
    schema = _provider_credential_schema(provider_id)
    if not schema:
        return provider_id in _LOCAL_PROVIDER_IDS
    return all(
        (not field.get("required", True)) or bool(os.environ.get(field["env"], "").strip())
        for field in schema
    )


def _persist_env_values(updates: Dict[str, str], removals=()) -> None:
    path = _credentials_path().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    remove_set = set(removals)
    with _SETTINGS_LOCK:
        original = path.read_text(encoding="utf-8") if path.is_file() else ""
        lines = original.splitlines()
        seen = set()
        output = []
        for line in lines:
            current = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
            if current in remove_set:
                continue
            if current in updates:
                output.append("%s=%s" % (current, updates[current]))
                seen.add(current)
            else:
                output.append(line)
        missing = [key for key in updates if key not in seen]
        if missing:
            if output and output[-1]:
                output.append("")
            output.append("# Credenciais configuradas pela Central de IAs do OLYMPUS")
            for key in missing:
                output.append("%s=%s" % (key, updates[key]))
        payload = ("\n".join(output).rstrip() + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".olympus-credentials-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(payload)
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def update_provider_credentials(provider_id: str, values: Dict[str, Any]) -> None:
    provider = str(provider_id or "").strip().lower()
    schema = _provider_credential_schema(provider)
    if not schema:
        raise KeyError(provider)
    by_id = {field["id"]: field for field in schema}
    supplied = {str(key): str(value or "").strip() for key, value in dict(values or {}).items()}
    unknown = sorted(set(supplied) - set(by_id))
    if unknown:
        raise ValueError("Campo de credencial desconhecido: %s" % ", ".join(unknown))
    updates = {}
    prospective = {field["id"]: os.environ.get(field["env"], "").strip() for field in schema}
    for field_id, value in supplied.items():
        field = by_id[field_id]
        if not value:
            continue
        if "\n" in value or "\r" in value or "\x00" in value or len(value) > int(field.get("max_length", 4096)):
            raise ValueError("Valor inválido para %s." % field["label"])
        pattern = field.get("pattern")
        if pattern and not __import__("re").match(pattern, value):
            raise ValueError("Formato inválido para %s." % field["label"])
        prospective[field_id] = value
        updates[field["env"]] = value
    missing = [field["label"] for field in schema if field.get("required", True) and not prospective.get(field["id"])]
    if missing:
        raise ValueError("Preencha os campos obrigatórios: %s." % ", ".join(missing))
    if not updates:
        raise ValueError("Nenhuma credencial nova foi informada.")
    _persist_env_values(updates)
    for key, value in updates.items():
        os.environ[key] = value


def remove_provider_credentials(provider_id: str) -> None:
    provider = str(provider_id or "").strip().lower()
    schema = _provider_credential_schema(provider)
    if not schema:
        raise KeyError(provider)
    env_names = tuple(field["env"] for field in schema)
    _persist_env_values({}, removals=env_names)
    for key in env_names:
        os.environ.pop(key, None)


def _provider_key_env(provider_id: str) -> str:
    return _PROVIDER_KEY_ENVS.get(provider_id, "%s_API_KEY" % provider_id.upper())


def _credentials_path() -> Path:
    configured = os.environ.get("OLYMPUS_CREDENTIALS_PATH", "").strip()
    return Path(configured).expanduser() if configured else _REPO_ROOT / "backend" / ".env"


def update_provider_secret(provider_id: str, secret: str) -> None:
    """Backward-compatible one-field credential update."""
    schema = _provider_credential_schema(provider_id)
    if not schema:
        raise KeyError(provider_id)
    primary = next((field for field in schema if field.get("secret", True)), schema[0])
    update_provider_credentials(provider_id, {primary["id"]: secret})


def remove_provider_secret(provider_id: str) -> None:
    """Backward-compatible removal now clears the provider credential set."""
    remove_provider_credentials(provider_id)


_PLUGIN_CATALOG = (
    {"id": "github", "name": "GitHub", "description": "Versionamento, repositórios e publicação."},
    {"id": "railway", "name": "Railway", "description": "Backend, variáveis protegidas e implantação."},
    {"id": "project_files", "name": "Arquivos do projeto", "description": "Leitura, edição, anexos e resultados para download."},
    {"id": "project_runtime", "name": "Preview e testes", "description": "Execução, preview responsivo e validação do projeto."},
    {"id": "higgsfield", "name": "Higgsfield Creative", "description": "Geração audiovisual assíncrona por API oficial, com autorização paga explícita."},
)

_FREE_PROVIDER_MODELS = {
    # FCC is catalog-only: no guessed model is ever called when the local
    # gateway is absent. Discovered models are filtered by _fcc_free_models.
    "fcc": (),
    "openrouter": (
        "openrouter/free",
    ),
    "groq": (
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "qwen/qwen3-32b",
        "groq/compound-mini",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ),
    "cerebras": (
        "qwen-3.8-27b",
        "gpt-oss-120b",
    ),
    "ollama": ("qwen2.5-coder:7b", "llama3.2"),
    "gemini": ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash"),
    "mistral": ("codestral-latest", "mistral-small-latest"),
    "zai": ("glm-4.7-flash", "glm-4.5-flash"),
    "cloudflare": ("@cf/qwen/qwen2.5-coder-32b-instruct",),
    # Zen exposes free and paid models through the same catalog. Only IDs
    # explicitly marked as free are allowed into the zero-cost chain.
    "opencode_zen": (
        "big-pickle", "mimo-v2.6-flash-free", "mimo-v2.5-free",
        "ling-3.0-flash-fin-free", "nemotron-3-ultra-free",
        "nemotron-3.5-lightning-free", "muse-spark-1.3-contributor-free",
        "jev-1.13-free",
    ),
}

_LOCAL_PROVIDER_IDS = {"fcc", "ollama"}


def _fcc_free_models(model_ids: Tuple[str, ...]) -> Tuple[str, ...]:
    """Keep only models whose FCC identity explicitly signals free/local use.

    FCC can also expose subscription and paid models.  Olympus must never
    infer that the whole gateway is free merely because FCC is local.
    Operators may provide an exact allow-list through OLYMPUS_FCC_FREE_MODELS.
    """
    configured = tuple(
        item.strip() for item in os.environ.get("OLYMPUS_FCC_FREE_MODELS", "").split(",")
        if item.strip()
    )
    available = tuple(dict.fromkeys(str(item).strip() for item in model_ids if str(item).strip()))
    if configured:
        existing = set(available)
        return tuple(item for item in configured if item in existing)
    free_prefixes = (
        "nvidia_nim/", "ollama/", "lmstudio/", "llamacpp/",
        "tokenrouter/", "nararoute/", "llm7/", "kilo/",
    )
    return tuple(
        item for item in available
        if item.lower().startswith(free_prefixes)
        or "/free" in item.lower()
        or ":free" in item.lower()
    )

_PAID_PROVIDER_MODELS = {
    "openai": ("gpt-5-mini",),
    "kimi": ("kimi-k2.5",),
}


def _opencode_zen_is_free(model_id: str) -> bool:
    value = str(model_id or "").strip().lower()
    return value == "big-pickle" or value.endswith("-free") or value.endswith(":free")


def _route_is_free(provider: str, model_id: str) -> bool:
    if provider == "opencode_zen":
        return _opencode_zen_is_free(model_id)
    return _PROVIDER_TIERS.get(provider) in {"free", "local"}


@dataclass(frozen=True)
class RoutingPolicy:
    mode: str = "free_first"
    free_attempt_limit: int = 6
    paid_fallback_authorized: bool = False
    paid_attempt_limit: int = 1
    paid_spend_cap_usd: float = 0.0


class SpendGuardRoutingAdapter:
    """Conservatively enforce a per-mission ceiling before paid API calls.

    Rates are intentionally high defaults and may be overridden when a
    provider changes its public pricing. If usage is absent, the full reserved
    amount is counted, so an unknown response can never make the guard looser.
    """
    _DEFAULT_RATES = {"openai": (5.0, 30.0), "kimi": (5.0, 30.0)}

    def __init__(self, adapter, cap_usd: float):
        self.adapter=adapter
        self.cap_usd=max(0.0,float(cap_usd))
        self.estimated_spend=0.0
        self._lock=threading.Lock()

    def health(self): return self.adapter.health()
    def list_models(self): return self.adapter.list_models()

    def _rate(self, provider):
        base=self._DEFAULT_RATES.get(provider,(10.0,40.0))
        prefix=f"OLYMPUS_{provider.upper()}"
        try:
            return (
                float(os.environ.get(f"{prefix}_INPUT_USD_PER_MILLION",base[0])),
                float(os.environ.get(f"{prefix}_OUTPUT_USD_PER_MILLION",base[1])),
            )
        except ValueError:
            return base

    def execute(self, model_id, prompt, *, max_tokens=None, temperature=None, **kwargs):
        provider,_model=split_provider_route(model_id,"omniroute")
        if _route_is_free(provider, _model):
            return self.adapter.execute(model_id,prompt,max_tokens=max_tokens,temperature=temperature,**kwargs)
        input_rate,output_rate=self._rate(provider)
        input_tokens=max(1,(len(str(prompt))+3)//4)
        output_tokens=max(1,int(max_tokens or 4096))
        reserved=(input_tokens*input_rate+output_tokens*output_rate)/1_000_000.0
        with self._lock:
            if self.estimated_spend + reserved > self.cap_usd:
                return RoutingExecutionResult(
                    model_id,"",provider,"",0,0.0,False,
                    "paid_budget_exhausted: conservative request estimate exceeds the authorized mission ceiling",
                    {"estimated_spend_usd":round(self.estimated_spend,6),"reserved_usd":round(reserved,6),"cap_usd":self.cap_usd},
                    "paid_budget_exhausted",
                )
        result=self.adapter.execute(model_id,prompt,max_tokens=max_tokens,temperature=temperature,**kwargs)
        usage=(result.metadata or {}).get("usage") or {}
        try:
            actual_input=int(usage.get("prompt_tokens") or usage.get("input_tokens") or input_tokens)
            actual_output=int(usage.get("completion_tokens") or usage.get("output_tokens") or output_tokens)
        except (TypeError,ValueError):
            actual_input,actual_output=input_tokens,output_tokens
        estimated=(actual_input*input_rate+actual_output*output_rate)/1_000_000.0
        with self._lock:
            self.estimated_spend += estimated
            running=self.estimated_spend
        metadata=dict(result.metadata or {})
        metadata.update({"estimated_cost_usd":round(estimated,6),"estimated_spend_usd":round(running,6),"cap_usd":self.cap_usd})
        return replace(result,cost=estimated,metadata=metadata)


def _load_settings() -> dict:
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _settings_path() -> Path:
    configured = os.environ.get("OLYMPUS_PROVIDER_SETTINGS_PATH", "").strip()
    return Path(configured).expanduser() if configured else _REPO_ROOT / ".olympus" / "provider-settings.json"


def _load_preferences() -> dict:
    data = _load_settings()
    providers = data.get("providers", {}) if isinstance(data, dict) else {}
    return providers if isinstance(providers, dict) else {}


def update_provider_preference(provider_id: str, *, enabled=None, priority=None, automatic=None) -> dict:
    """Persist non-secret routing preferences atomically.

    Credentials remain in the protected environment file.  This store only
    contains booleans and numeric ordering, so it is safe to inspect and copy.
    """
    provider = str(provider_id or "").strip().lower()
    if provider not in _PROVIDER_LABELS:
        raise KeyError(provider)
    if priority is not None and not 1 <= int(priority) <= 999:
        raise ValueError("priority must be between 1 and 999")
    with _SETTINGS_LOCK:
        preferences = _load_preferences()
        current = dict(preferences.get(provider, {}))
        if enabled is not None:
            current["enabled"] = bool(enabled)
        if priority is not None:
            current["priority"] = int(priority)
        if automatic is not None:
            current["automatic"] = bool(automatic)
        preferences[provider] = current
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".provider-settings-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
                existing = _load_settings()
                existing["providers"] = preferences
                json.dump(existing, destination, ensure_ascii=False, indent=2, sort_keys=True)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return dict(current)


def routing_policy(override=None) -> RoutingPolicy:
    raw = dict(_load_settings().get("routing_policy") or {})
    if override:
        raw.update({key: value for key, value in dict(override).items() if value is not None})
    mode = str(raw.get("mode") or "free_first")
    if mode not in {"free_first", "protected", "premium_direct"}:
        mode = "free_first"
    return RoutingPolicy(
        mode=mode,
        free_attempt_limit=min(8, max(1, int(raw.get("free_attempt_limit", 6)))),
        paid_fallback_authorized=bool(raw.get("paid_fallback_authorized", False)),
        paid_attempt_limit=min(3, max(1, int(raw.get("paid_attempt_limit", 1)))),
        paid_spend_cap_usd=max(0.0, min(1000.0, float(raw.get("paid_spend_cap_usd", 0.0)))),
    )


def update_routing_policy(**changes) -> dict:
    current = asdict(routing_policy(changes))
    # Paid routes require an explicit positive cap. This prevents a checkbox
    # or stale preference from becoming open-ended spending authority.
    if current["paid_fallback_authorized"] and current["paid_spend_cap_usd"] <= 0:
        raise ValueError("Defina um limite de gasto maior que zero para autorizar rotas pagas.")
    with _SETTINGS_LOCK:
        data = _load_settings()
        data["routing_policy"] = current
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".provider-settings-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
                json.dump(data, destination, ensure_ascii=False, indent=2, sort_keys=True)
                destination.write("\n")
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return current


def _preference(provider_id: str, default_enabled: bool, default_priority: int) -> tuple[bool, int]:
    configured = _load_preferences().get(provider_id, {})
    enabled = bool(configured.get("enabled", default_enabled))
    try:
        priority = int(configured.get("priority", default_priority))
    except (TypeError, ValueError):
        priority = default_priority
    return enabled, min(999, max(1, priority))


def build_provider_registry(timeout_seconds: float = 2) -> ProviderRegistry:
    """Build providers without performing network calls or exposing keys."""
    registry = ProviderRegistry()
    omniroute_enabled, omniroute_priority = _preference("omniroute", True, 10)
    omniroute = OmniRouteAdapter(
        base_url=os.environ.get("OLYMPUS_OMNIROUTE_URL", "http://127.0.0.1:20128"),
        api_key=(os.environ.get("OLYMPUS_OMNIROUTE_API_KEY") or os.environ.get("OMNIROUTE_API_KEY") or None),
        timeout_seconds=timeout_seconds,
    )
    # OmniRoute has no native enabled flag; wrap the setting on the instance so
    # the generic registry and catalog can consistently suppress it.
    if not omniroute_enabled:
        omniroute.health = lambda: RoutingHealth(False, "omniroute", "disabled")
    registry.register(
        "omniroute",
        omniroute,
        priority=omniroute_priority,
    )
    for provider_id, _label, url_env, default_url, key_env, priority, _cost in _DIRECT_PROVIDERS:
        key = (os.environ.get(key_env) or None) if key_env else None
        credentials_ready = provider_id in _LOCAL_PROVIDER_IDS or _provider_credentials_configured(provider_id)
        requested, configured_priority = _preference(provider_id, credentials_ready, priority)
        base_url = os.environ.get(url_env, default_url).strip()
        catalog_url = None
        if provider_id == "cloudflare":
            account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
            if account_id and not base_url:
                api_root = "https://api.cloudflare.com/client/v4/accounts/%s/ai" % account_id
                base_url = api_root + "/v1"
                catalog_url = api_root + "/models/search"
            elif account_id:
                catalog_url = "https://api.cloudflare.com/client/v4/accounts/%s/ai/models/search" % account_id
        enabled = requested and bool(base_url) and credentials_ready
        config = ProviderConfig(
            provider_id,
            base_url,
            key,
            enabled=enabled,
            timeout_seconds=int(timeout_seconds),
            wire_api="responses" if provider_id == "fcc" else "chat_completions",
            catalog_url=catalog_url,
        )
        if provider_id == "cloudflare":
            adapter = CloudflareWorkersAIAdapter(config)
        elif provider_id == "gemini":
            adapter = GeminiNativeAdapter(config)
        else:
            adapter = OpenAICompatibleAdapter(config)
        registry.register(provider_id, adapter, priority=configured_priority)
    return registry


def provider_catalog(timeout_seconds: float = 2) -> dict:
    """Return the product-facing AI and plugin inventory without secrets."""
    registry = build_provider_registry(timeout_seconds)
    health_by_id = {item.provider: item for item in registry.health_all()}
    preferences = _load_preferences()
    allowed_fallbacks = set(_allowed_fallbacks())
    capacity = capacity_fabric_snapshot()
    capacity_providers = {row.get("id"): row for row in capacity.get("providers", [])}
    capacity_routes = capacity.get("routes", [])
    providers = []
    definitions = [
        ("omniroute", "OmniRoute", None, 10, "Roteador local", "Gateway automático para modelos disponíveis."),
    ] + [
        (provider_id, label, key_env, priority, cost, "Provedor de inteligência compatível com o Olympus.")
        for provider_id, label, _url_env, _url, key_env, priority, cost in _DIRECT_PROVIDERS
    ]
    for provider_id, label, key_env, default_priority, cost, description in definitions:
        if provider_id == "omniroute":
            credential_configured = _provider_credentials_configured("omniroute")
        else:
            credential_configured = provider_id in _LOCAL_PROVIDER_IDS or key_env is None or _provider_credentials_configured(provider_id)
        default_enabled = provider_id in ("omniroute",) or provider_id in _LOCAL_PROVIDER_IDS or credential_configured
        enabled, priority = _preference(provider_id, default_enabled, default_priority)
        if key_env and not credential_configured:
            enabled = False
        health = health_by_id.get(provider_id)
        status = health.status if health else "unavailable"
        models = list((health.metadata or {}).get("models", ())) if health and health.healthy else []
        model_count = int((health.metadata or {}).get("models_count", len(models))) if health else 0
        automatic = preferences.get(provider_id, {}).get("automatic")
        cap_provider = capacity_providers.get(provider_id, {})
        cap_rows = [row for row in capacity_routes if row.get("provider") == provider_id]
        cap_counts = {state: sum(1 for row in cap_rows if row.get("state") == state) for state in ("ready", "candidate", "degraded", "cooldown", "quarantined")}
        providers.append({
            "id": provider_id,
            "name": label,
            "description": (
                "Ponte local opcional para o catálogo do Free Claude Code; somente modelos gratuitos ou locais identificados entram automaticamente."
                if provider_id == "fcc" else description
            ),
            "cost": cost,
            "tier": _PROVIDER_TIERS.get(provider_id, "paid"),
            "configured": credential_configured,
            "enabled": enabled,
            "priority": priority,
            "healthy": bool(health and health.healthy),
            "status": status,
            "automatic_active": enabled and (
                (provider_id == "omniroute" and automatic is not False)
                or provider_id in allowed_fallbacks
                or (_PROVIDER_TIERS.get(provider_id) == "paid" and automatic is True)
            ),
            "model_count": model_count,
            "models": models[:50],
            "safe_free_model_count": len(_fcc_free_models(tuple(models))) if provider_id == "fcc" else None,
            "external_gateway": provider_id == "fcc",
            "capacity_state": cap_provider.get("state", "candidate"),
            "capacity_counts": cap_counts,
            "capacity_cooldown_until": float(cap_provider.get("cooldown_until") or 0.0),
            "preference_saved": provider_id in preferences,
            "credential_fields": provider_credential_fields(provider_id),
        })
    providers.sort(key=lambda item: (item["priority"], item["name"]))
    return {
        "providers": providers,
        "plugins": list(_PLUGIN_CATALOG),
        "automatic_failover": True,
        "routing_policy": asdict(routing_policy()),
        "capacity_fabric": {"counts": capacity.get("counts", {}), "updated_at": capacity.get("updated_at", 0.0)},
    }


def _trusted_live_agent_routes(provider_id: str) -> Tuple[str, ...]:
    """Routes proven by READY_AGENT v2 and an isolated real AgentLoop mission."""
    provider = str(provider_id or "").strip().lower()
    trusted = []
    for row in capacity_fabric_snapshot().get("routes", ()):
        if (
            row.get("provider") == provider
            and row.get("qualified")
            and row.get("qualification_level") == "agent_route_v2"
            and row.get("live_agent_proof") is True
        ):
            route_id = str(row.get("route_id") or "").strip()
            if route_id:
                trusted.append(route_id)
    return tuple(dict.fromkeys(trusted))


def _allowed_fallbacks() -> Tuple[str, ...]:
    # Cerebras is kept as an opt-in integration because a healthy key may
    # still have no inference quota. Default zero-cost routing uses Groq only.
    # Ollama is zero-cost and local. Include it in the default chain, but its
    # adapter still performs a real /models check before it can be selected.
    # An uninstalled Ollama therefore fails closed and does not block startup.
    raw = os.environ.get("OLYMPUS_FREE_FALLBACK_PROVIDERS", "fcc,groq,openrouter,ollama,opencode_zen")
    configured_defaults = {value.strip().lower() for value in raw.split(",") if value.strip()}
    preferences = _load_preferences()
    allowed = []
    for provider in _FREE_PROVIDER_MODELS:
        automatic = preferences.get(provider, {}).get("automatic")
        if automatic is False or (automatic is not True and provider not in configured_defaults):
            continue
        if automatic is not True and provider in ("cerebras", "gemini", "mistral", "zai", "cloudflare") and os.environ.get(
            "OLYMPUS_ENABLE_METERED_PROVIDERS", ""
        ).strip().lower() not in ("1", "true", "yes"):
            continue
        # Sensitive free-paid routes require both READY_AGENT v2 and an isolated
        # real AgentLoop proof before automatic use.
        if provider in ("together", "ollama_cloud") and not _trusted_live_agent_routes(provider):
            continue
        enabled, _priority = _preference(
            provider,
            provider in _LOCAL_PROVIDER_IDS or _provider_credentials_configured(provider),
            100,
        )
        if provider in _FREE_PROVIDER_MODELS and enabled and provider not in allowed:
            allowed.append(provider)
    return tuple(sorted(allowed, key=lambda item: _preference(item, True, 100)[1]))


def _rank_live_models(model_ids: Tuple[str, ...]) -> Tuple[str, ...]:
    """Prefer coding/chat models and suppress audio or safety-only endpoints."""
    blocked = (
        "whisper", "guard", "safeguard", "orpheus", "audio", "speech", "tts",
        # Arabic-specialized chat model; it repeatedly reaches the end of the
        # coding fallback chain without producing compatible repository actions.
        "allam",
    )
    usable = [model for model in model_ids if not any(token in model.lower() for token in blocked)]

    def score(model: str):
        value = model.lower()
        priorities = (
            # Gemini native catalog is already filtered to generateContent-capable
            # text/chat models. Prefer current Flash families for low-latency agent
            # actions before falling back to older generations.
            "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash",
            "gemini-3.5-flash-lite", "gemini-3.1-flash", "gemini-3-flash",
            "gemini-2.5-flash",
            "qwen3.8", "qwen3.6", "qwen3", "coder", "gpt-oss",
            "compound-mini", "compound", "llama", "deepseek",
        )
        rank = next((index for index, token in enumerate(priorities) if token in value), len(priorities))
        return rank, value

    return tuple(sorted(dict.fromkeys(usable), key=score))


def _omniroute_explicit_free_models(model_ids: Tuple[str, ...]) -> Tuple[str, ...]:
    """Return only catalog models whose identity explicitly guarantees free use.

    The generic OpenRouter router remains the first attempt, but concrete
    ``:free`` models provide observable, bounded fallback identities when the
    dynamic route times out or yields an empty response.  Paid or ambiguous
    catalog entries are never inferred as free.
    """
    def is_meta_route(model: str) -> bool:
        value = model.lower().strip()
        return (
            value == FREE_ROUTER_MODEL_ID.lower()
            or value.startswith("auto/")
            or "/auto/" in value
            or "best-coding" in value
            or value.endswith("/coding:free")
        )

    explicit = tuple(
        model for model in model_ids
        if not is_meta_route(model)
        and (
            model.lower().endswith(":free")
            or "/free/" in model.lower()
            or model.lower().endswith("/free")
        )
    )

    # Prefer concrete coding models observed in the live catalog.  Meta routes
    # are deliberately excluded above because they can select the same broken
    # upstream repeatedly while looking like an independent fallback.
    priorities = (
        "north-mini-code",
        "nemotron-3-super",
        "nemotron-3.5-lightning",
        "nemotron-3-nano",
        "gemma-4-31b",
        "gemma-4-26b",
        "dots-3",
        "gpt-oss",
        "lfm-",
        "coder",
    )

    def score(model: str):
        value = model.lower()
        rank = next(
            (index for index, token in enumerate(priorities) if token in value),
            len(priorities),
        )
        return rank, value

    return tuple(sorted(dict.fromkeys(explicit), key=score))


def _omniroute_pool_status() -> dict:
    path = _REPO_ROOT / ".olympus" / "runtime" / "omniroute-pools.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Optional tiers and probe-derived candidates are ephemeral runtime facts.
    # Do not trust a READY marker forever: a provider/model that worked yesterday
    # may be offline or quota-blocked today. The proven baseline combo remains
    # usable even when the optional pool snapshot is stale.
    try:
        raw_updated_at = data.get("updated_at")
        max_age = max(60.0, float(os.environ.get("OLYMPUS_OMNIROUTE_POOL_MAX_AGE_SECONDS", "21600")))
        # Legacy snapshots written before freshness tracking did not include
        # updated_at. Keep them compatible; every current sync writes updated_at,
        # so real runtime snapshots are age-checked from now on.
        if raw_updated_at in (None, ""):
            data["_fresh"] = True
        else:
            updated_at = float(raw_updated_at)
            data["_fresh"] = bool(updated_at and (time.time() - updated_at) <= max_age)
    except (TypeError, ValueError):
        data["_fresh"] = False
    return data


def _omniroute_tier_routes(selection_priority: int) -> Tuple[AgentModelRoute, ...]:
    """Known-good hierarchy: free combo -> Ollama local -> Ollama Cloud.

    The status file is written only after real inference probes. Missing or stale
    optional tiers therefore fail closed while the original OpenRouter route
    remains available later in configured_free_routes.
    """
    status = _omniroute_pool_status()
    routes = []
    primary = str(status.get("primary_combo") or "Conding-free").strip() or "Conding-free"
    # Conding-free is the proven E2E baseline and is never gated on discovery.
    # Pool sync can add optional routes, but it cannot remove this first route.
    routes.append(AgentModelRoute(
        primary,
        "OmniRoute proven free combo — %s" % primary,
        "conding_free",
        selection_priority,
        200000,
    ))
    snapshot_fresh = bool(status.get("_fresh"))
    local_ready = tuple(str(x).strip() for x in (status.get("ollama_local_ready") or ()) if str(x).strip()) if snapshot_fresh else ()
    if local_ready:
        routes.append(AgentModelRoute(
            local_ready[0],
            "Ollama Local via OmniRoute — %s" % local_ready[0],
            "ollama_local",
            selection_priority - 10,
        ))
    cloud_ready = tuple(str(x).strip() for x in (status.get("ollama_cloud_ready") or ()) if str(x).strip()) if snapshot_fresh else ()
    if cloud_ready:
        routes.append(AgentModelRoute(
            cloud_ready[0],
            "Ollama Cloud via OmniRoute — %s" % cloud_ready[0],
            "ollama_cloud",
            selection_priority - 20,
        ))
    expanded = str(status.get("expanded_combo") or "").strip()
    if snapshot_fresh and status.get("expanded_combo_ready") and expanded and expanded != primary:
        routes.append(AgentModelRoute(
            expanded,
            "Expanded explicit-free shadow combo — %s" % expanded,
            "conding_free_expanded",
            selection_priority - 30,
            200000,
        ))
    return tuple(routes)


def configured_free_routes(registry=None) -> Tuple[AgentModelRoute, ...]:
    """Return only routes whose independent provider credential exists.

    OpenRouter remains the primary free router through OmniRoute. Direct
    providers are opt-in by placing their own key in ``backend/.env``; no key
    is bundled, logged or inferred.
    """
    preferences = _load_preferences()
    omniroute_enabled, omniroute_priority = _preference("omniroute", True, 10)
    omniroute_automatic = preferences.get("omniroute", {}).get("automatic", True)
    routes = []
    ordered_providers = []
    if omniroute_enabled and omniroute_automatic is not False:
        ordered_providers.append((omniroute_priority, "omniroute"))
    ordered_providers.extend(
        (_preference(provider_id, True, 100)[1], provider_id)
        for provider_id in _allowed_fallbacks()
    )
    # Metered/free-paid providers such as Ollama Cloud direct are never enabled
    # automatically. They can join the free-first continuation only after the
    # administrator explicitly opts in via the Olympus UI.
    for provider_id in _PROVIDER_LABELS:
        if provider_id in {"omniroute"} or provider_id in _allowed_fallbacks():
            continue
        if _PROVIDER_TIERS.get(provider_id) != "free_paid":
            continue
        automatic = preferences.get(provider_id, {}).get("automatic")
        if automatic is not True or not _provider_credentials_configured(provider_id):
            continue
        if provider_id in ("together", "ollama_cloud") and not _trusted_live_agent_routes(provider_id):
            continue
        ordered_providers.append((_preference(provider_id, True, 300)[1], provider_id))
    ordered_providers.sort(key=lambda item: (item[0], item[1]))

    # The Central uses smaller numbers as earlier attempts, while the legacy
    # DecisionEngine ranks a larger model ``prioridade`` first. Translate the
    # user-facing order here so the route displayed first is really tried first.
    for configured_priority, provider_id in ordered_providers:
        selection_priority = 1_000_000 - (configured_priority * 1_000)
        if provider_id == "omniroute":
            # Preserve the proven path first, then optional Ollama tiers.  These
            # routes are unqualified model IDs, so execution still flows through
            # the same authenticated OmniRoute adapter. Their logical provider
            # labels only isolate failover domains in the control plane.
            tier_routes = _omniroute_tier_routes(selection_priority)
            routes.extend(tier_routes)
            used = len(tier_routes)

            explicit_models = ()
            if registry is not None:
                try:
                    catalog_ids = tuple(
                        item.model_id
                        for item in registry.adapter("omniroute").list_models()
                        if item.available and item.model_id
                    )
                except Exception:
                    catalog_ids = ()
                explicit_models = _omniroute_explicit_free_models(catalog_ids)
                # Models that passed a recent real inference probe should be tried
                # before merely-discovered catalog entries. This keeps a stale or
                # historically-ranked model from consuming the only free failover
                # slot while a freshly verified model is available.
                pool = _omniroute_pool_status()
                verified = tuple(
                    str(x).strip() for x in (pool.get("openrouter_new_probe_ready") or ())
                    if pool.get("_fresh") and str(x).strip()
                )
                explicit_models = tuple(dict.fromkeys(verified + explicit_models))

            # Legacy explicit-free routes remain after the three-tier baseline.
            # They are intentionally not removed, so an unavailable optional
            # Ollama route can never reduce the resilience we already had.
            for model_offset, model_id in enumerate(explicit_models):
                routes.append(AgentModelRoute(
                    model_id,
                    "OmniRoute explicit free model — %s" % model_id,
                    model_id.split("/", 1)[0],
                    selection_priority - 100 - model_offset,
                ))
            routes.append(AgentModelRoute(
                FREE_ROUTER_MODEL_ID,
                "OpenRouter Free Models Router",
                "openrouter",
                selection_priority - 200 - len(explicit_models),
                200000,
            ))
            continue
        key_name = _provider_key_env(provider_id)
        if provider_id not in _LOCAL_PROVIDER_IDS and not _provider_credentials_configured(provider_id):
            continue
        model_env = "OLYMPUS_%s_MODELS" % provider_id.upper()
        configured_models = os.environ.get(model_env, "")
        models = tuple(
            model.strip() for model in configured_models.split(",") if model.strip()
        )
        live_catalog = False
        live_probe_attempted = registry is not None
        if registry is not None:
            try:
                live_models = tuple(
                    item.model_id for item in registry.adapter(provider_id).list_models()
                    if item.available
                )
            except Exception:
                live_models = ()
            if live_models:
                live_catalog = True
            if models:
                available = set(live_models)
                models = tuple(model for model in models if model in available)
            else:
                models = _rank_live_models(live_models)
            if provider_id == "opencode_zen":
                models = tuple(model for model in models if _opencode_zen_is_free(model))
            # A runtime registry means we had a chance to perform live discovery.
            # If that provider exposes no usable model now, fail closed instead of
            # resurrecting a hard-coded fallback. This is especially important for
            # local Ollama: an installed model name must never be interpreted as a
            # READY route when the daemon itself is unreachable.
            if not live_models:
                continue
        if provider_id == "fcc":
            models = _fcc_free_models(tuple(models))
            if not models:
                continue
        if not models and not live_catalog:
            if provider_id not in _FREE_PROVIDER_MODELS:
                # No hard-coded model names for metered/free-paid providers.
                # They must expose a live catalog before they can be routed.
                continue
            models = _FREE_PROVIDER_MODELS[provider_id]
        if provider_id == "opencode_zen":
            models = tuple(model for model in models if _opencode_zen_is_free(model))
        for model_offset, model_id in enumerate(models):
            routes.append(AgentModelRoute(
                provider_route_id(provider_id, model_id),
                "%s free fallback — %s" % (provider_id.title(), model_id),
                provider_id,
                selection_priority - model_offset,
            ))
    return tuple(routes)


def _diversified_limit(routes, limit):
    """Try independent providers before spending attempts on sibling models."""
    primary=[]; remainder=[]; seen=set()
    for route in routes:
        if route.provider not in seen:
            primary.append(route); seen.add(route.provider)
        else:
            remainder.append(route)
    return tuple((primary + remainder)[:limit])


def _agent_compatible_routes(routes):
    """Exclude known specialist APIs that cannot produce coding-agent actions."""
    eligible = []
    for route in routes:
        model = str(route.id).lower().split("::")[-1].split("/")[-1]
        # NVIDIA Content Safety returns moderation labels. OpenCode Jev uses
        # System One typed decisions rather than text/chat completions.
        if "content-safety" in model or model.startswith("jev-"):
            continue

        # Batch variants use a different execution contract/endpoint and
        # cannot participate in the interactive coding-agent chat loop.
        # Exclude only the incompatible route, never the whole provider.
        if model.endswith(":batch"):
            continue

        # OpenCode Zen may expose free catalog entries whose trial policy only
        # permits execution from inside the OpenCode client. A real Olympus
        # mission proved exo-free returns FreeTierError for external API use.
        # Exclude that route only; other Zen models remain eligible.
        if route.provider == "opencode_zen" and model == "exo-free":
            continue

        eligible.append(route)
    return tuple(eligible)


def configured_mission_routes(registry=None, policy_override=None) -> Tuple[AgentModelRoute, ...]:
    policy = routing_policy(policy_override)
    free = _diversified_limit(capacity_filter_routes(
        _agent_compatible_routes(configured_free_routes(registry))
    ), policy.free_attempt_limit)
    paid=[]
    if policy.paid_fallback_authorized and policy.paid_spend_cap_usd > 0:
        paid_definitions = dict(_PAID_PROVIDER_MODELS)
        if "opencode_zen" in _PROVIDER_LABELS:
            live_models = ()
            if registry is not None:
                try:
                    live_models = tuple(
                        item.model_id for item in registry.adapter("opencode_zen").list_models()
                        if item.available and not _opencode_zen_is_free(item.model_id)
                    )
                except Exception:
                    live_models = ()
            paid_definitions["opencode_zen"] = live_models
        for provider_id, models in paid_definitions.items():
            key_env = _provider_key_env(provider_id)
            enabled, priority = _preference(provider_id, _provider_credentials_configured(provider_id), 500)
            automatic = _load_preferences().get(provider_id, {}).get("automatic")
            if not enabled or automatic is not True or not _provider_credentials_configured(provider_id):
                continue
            selection_priority = 500_000 - priority * 100
            configured = os.environ.get(f"OLYMPUS_{provider_id.upper()}_MODELS", "")
            selected = tuple(item.strip() for item in configured.split(",") if item.strip()) or tuple(models)
            for offset, model_id in enumerate(selected):
                paid.append(AgentModelRoute(
                    provider_route_id(provider_id, model_id),
                    f"{provider_id.title()} paid continuation — {model_id}",
                    provider_id,
                    selection_priority - offset,
                    tier="paid",
                ))
    paid = list(_diversified_limit(capacity_filter_routes(
        _agent_compatible_routes(tuple(paid))
    ), policy.paid_attempt_limit))
    if policy.mode == "premium_direct":
        return tuple(paid)
    if policy.mode == "protected":
        return tuple(free) + tuple(paid)
    return tuple(free)


def build_mission_routing(timeout_seconds: float, policy_override=None):
    registry = build_provider_registry(timeout_seconds)
    policy = routing_policy(policy_override)
    routes = configured_mission_routes(registry, policy_override)
    adapter = MultiProviderRoutingAdapter(registry, default_provider="omniroute")
    adapter = CapacityAwareRoutingAdapter(adapter)
    if policy.paid_fallback_authorized:
        adapter = SpendGuardRoutingAdapter(adapter, policy.paid_spend_cap_usd)
    return (
        adapter,
        OlympusModelSelector(routes),
    )


def build_visual_review_routing(timeout_seconds=20):
    """Use existing administrator-selected free routes; never paid fallback."""
    registry = build_provider_registry(timeout_seconds)
    routes = configured_free_routes(registry)
    eligible = tuple(route.id for route in capacity_filter_routes(routes) if route.tier in {'free','local'})
    adapter = CapacityAwareRoutingAdapter(MultiProviderRoutingAdapter(registry,default_provider='omniroute'))
    return adapter, eligible


def build_delivery_verifier(workspace, routing_factory=None):
    """Shared HUB quality boundary for project missions and the older tester."""
    from olympus.agent.verifier import AgentVerifier
    from olympus.agent.visual_delivery import VisualDeliveryReviewer
    return AgentVerifier(workspace,visual_reviewer=VisualDeliveryReviewer(
        routing_factory=routing_factory or build_visual_review_routing))
