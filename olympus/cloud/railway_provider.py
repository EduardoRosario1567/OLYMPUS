from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import RLock
from typing import Callable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import re
import sqlite3
import tempfile
import time

from .deployment import DeploymentPolicyError, DeploymentRequest, ProviderDeployment, ProviderDnsRecord


RAILWAY_GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
MAX_RAILWAY_RESPONSE_BYTES = 4 * 1024 * 1024

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REVISION = re.compile(r"^[a-fA-F0-9]{7,64}$")
_RAILWAY_STATUS = {
    "BUILDING": "building",
    "DEPLOYING": "building",
    "QUEUED": "queued",
    "WAITING": "queued",
    "SUCCESS": "ready",
    "FAILED": "failed",
    "CRASHED": "failed",
    "REMOVED": "failed",
    "SKIPPED": "failed",
    "SLEEPING": "ready",
}


class RailwayApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)


class RailwayApi:
    """Minimal fixed-origin Railway GraphQL client; credentials are never logged."""

    def __init__(self, token: str, timeout_seconds: int = 20) -> None:
        clean = str(token or "").strip()
        if len(clean) < 20 or len(clean) > 512 or any(char in clean for char in "\r\n\x00"):
            raise ValueError("Token do Railway inválido.")
        self._token = clean
        self.timeout_seconds = max(3, min(60, int(timeout_seconds)))

    def execute(self, query: str, variables: Optional[dict] = None) -> dict:
        if not isinstance(query, str) or len(query) < 10 or len(query) > 32_000:
            raise ValueError("Operação Railway inválida.")
        body = json.dumps({"query": query, "variables": variables or {}}, ensure_ascii=False).encode("utf-8")
        request = Request(
            RAILWAY_GRAPHQL_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json",
                "User-Agent": "OLYMPUS-Professional/2.0",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read(MAX_RAILWAY_RESPONSE_BYTES + 1)
                if len(content) > MAX_RAILWAY_RESPONSE_BYTES:
                    raise RailwayApiError(502, "A resposta do Railway excedeu o limite seguro.")
                result = json.loads(content.decode("utf-8")) if content else {}
        except HTTPError as exc:
            exc.read(64 * 1024)
            raise RailwayApiError(exc.code, "A API do Railway recusou a operação.") from None
        except (URLError, TimeoutError, OSError):
            raise RailwayApiError(503, "Não foi possível alcançar o Railway.") from None
        except (UnicodeError, ValueError):
            raise RailwayApiError(502, "O Railway retornou uma resposta inválida.") from None
        if not isinstance(result, dict):
            raise RailwayApiError(502, "O Railway retornou uma resposta inválida.")
        if result.get("errors"):
            # Provider messages may echo user input or variables; keep the UI response generic.
            raise RailwayApiError(400, "O Railway não aceitou a configuração enviada.")
        data = result.get("data")
        if not isinstance(data, dict):
            raise RailwayApiError(502, "O Railway retornou uma resposta incompleta.")
        return data

    def account(self) -> dict:
        return self.execute("query { me { id name email } }").get("me") or {}

    def service(self, service_id: str) -> dict:
        return self.execute(
            "query service($id: String!) { service(id: $id) { id name projectId } }",
            {"id": service_id},
        ).get("service") or {}

    def service_instance(self, service_id: str, environment_id: str) -> dict:
        return self.execute(
            "query serviceInstance($serviceId: String!, $environmentId: String!) { "
            "serviceInstance(serviceId: $serviceId, environmentId: $environmentId) { id serviceName latestDeployment { id status createdAt } } }",
            {"serviceId": service_id, "environmentId": environment_id},
        ).get("serviceInstance") or {}

    def upsert_variables(self, project_id: str, environment_id: str, service_id: str, variables: Mapping[str, str]) -> None:
        self.execute(
            "mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) { variableCollectionUpsert(input: $input) }",
            {"input": {"projectId": project_id, "environmentId": environment_id, "serviceId": service_id,
                       "variables": dict(variables), "replace": False, "skipDeploys": True}},
        )

    def deploy_service(self, service_id: str, environment_id: str) -> str:
        value = self.execute(
            "mutation serviceInstanceDeployV2($serviceId: String!, $environmentId: String!) { "
            "serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId) }",
            {"serviceId": service_id, "environmentId": environment_id},
        ).get("serviceInstanceDeployV2")
        return str(value or "")

    def deployment(self, deployment_id: str) -> dict:
        return self.execute(
            "query deployment($id: String!) { deployment(id: $id) { id status url staticUrl meta canRollback } }",
            {"id": deployment_id},
        ).get("deployment") or {}

    def rollback(self, target_deployment_id: str) -> dict:
        return self.execute(
            "mutation deploymentRollback($id: String!) { deploymentRollback(id: $id) { id status url staticUrl meta } }",
            {"id": target_deployment_id},
        ).get("deploymentRollback") or {}

    def create_domain(self, project_id: str, environment_id: str, service_id: str, domain: str) -> dict:
        available = self.execute(
            "query customDomainAvailable($domain: String!) { customDomainAvailable(domain: $domain) { available message } }",
            {"domain": domain},
        ).get("customDomainAvailable") or {}
        if not available.get("available"):
            raise RailwayApiError(409, "O domínio informado não está disponível no Railway.")
        return self.execute(
            "mutation customDomainCreate($input: CustomDomainCreateInput!) { customDomainCreate(input: $input) { "
            "id domain status { verificationToken dnsRecords { hostlabel requiredValue status } } } }",
            {"input": {"projectId": project_id, "environmentId": environment_id,
                       "serviceId": service_id, "domain": domain}},
        ).get("customDomainCreate") or {}


@dataclass(frozen=True)
class RailwayBinding:
    tenant_id: str
    project_id: str
    railway_project_id: str
    service_id: str
    environment_id: str
    repository: str
    connected_at: float
    updated_at: float


class RailwayBindingStore:
    """Stores only routing metadata. Railway credentials never enter this file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._records = self._load()

    @staticmethod
    def _key(project_id: str, tenant_id: str) -> str:
        return "%s:%s" % (tenant_id, project_id)

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".railway-bindings-", dir=str(self.path.parent))
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self._records, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def get(self, project_id: str, tenant_id: str) -> Optional[RailwayBinding]:
        with self._lock:
            value = self._records.get(self._key(project_id, tenant_id))
            try:
                return RailwayBinding(**value) if isinstance(value, dict) else None
            except (TypeError, ValueError):
                return None

    def put(self, binding: RailwayBinding) -> RailwayBinding:
        with self._lock:
            self._records[self._key(binding.project_id, binding.tenant_id)] = asdict(binding)
            self._save()
        return binding

    def remove(self, project_id: str, tenant_id: str) -> bool:
        with self._lock:
            removed = self._records.pop(self._key(project_id, tenant_id), None) is not None
            if removed:
                self._save()
            return removed


class SQLiteRailwayDeploymentBindingStore:
    """Persistent provider routing for domain and rollback after restart."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS railway_deployment_bindings (deployment_id TEXT PRIMARY KEY, binding TEXT NOT NULL)"
            )
        os.chmod(self.path, 0o600)

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def put(self, deployment_id: str, binding: RailwayBinding) -> None:
        identifier = _identifier(deployment_id, "Deployment")
        payload = json.dumps(asdict(binding), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = connection.execute(
                    "SELECT binding FROM railway_deployment_bindings WHERE deployment_id=?", (identifier,)
                ).fetchone()
                if current is not None and current[0] != payload:
                    raise DeploymentPolicyError("Deployment Railway já pertence a outro serviço.")
                connection.execute(
                    "INSERT OR IGNORE INTO railway_deployment_bindings(deployment_id,binding) VALUES(?,?)",
                    (identifier, payload),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def get(self, deployment_id: str) -> Optional[RailwayBinding]:
        identifier = _identifier(deployment_id, "Deployment")
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT binding FROM railway_deployment_bindings WHERE deployment_id=?", (identifier,)
            ).fetchone()
        if row is None:
            return None
        try:
            return RailwayBinding(**json.loads(row[0]))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Railway deployment binding is corrupted") from exc


def _identifier(value: str, label: str) -> str:
    clean = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(clean):
        raise ValueError("%s inválido." % label)
    return clean


def _repository(value: str) -> str:
    clean = str(value or "").strip()
    if not _REPOSITORY.fullmatch(clean) or ".." in clean:
        raise ValueError("Repositório inválido.")
    return clean


def _provider_url(value: dict) -> Optional[str]:
    url = value.get("staticUrl") or value.get("url")
    if not url:
        return None
    clean = str(url).strip()
    return clean if clean.startswith("https://") else "https://" + clean


def _revision_from_meta(meta: object) -> Optional[str]:
    if not isinstance(meta, dict):
        return None
    for key in ("commitHash", "commitSha", "commit", "revision"):
        value = str(meta.get(key) or "").strip()
        if _REVISION.fullmatch(value):
            return value.lower()
    return None


class RailwayProvider:
    provider_id = "railway"

    def __init__(self, bindings: RailwayBindingStore, token_resolver: Callable[[str], str], api_factory: Callable[[str], RailwayApi] = RailwayApi,
                 deployment_store: Optional[SQLiteRailwayDeploymentBindingStore] = None) -> None:
        self.bindings = bindings
        self.token_resolver = token_resolver
        self.api_factory = api_factory
        self._deployment_bindings: dict[str, RailwayBinding] = {}
        self._lock = RLock()
        self.deployment_store = deployment_store

    def _deployment_binding(self, deployment_id: str) -> Optional[RailwayBinding]:
        with self._lock:
            value = self._deployment_bindings.get(deployment_id)
        if value is None and self.deployment_store is not None:
            value = self.deployment_store.get(deployment_id)
        return value

    def _remember_deployment(self, deployment_id: str, binding: RailwayBinding) -> None:
        if self.deployment_store is not None:
            self.deployment_store.put(deployment_id, binding)
        with self._lock:
            self._deployment_bindings[deployment_id] = binding

    def _api_for(self, tenant_id: str) -> RailwayApi:
        token = self.token_resolver(tenant_id)
        if not token:
            raise DeploymentPolicyError("Railway não conectado para esta organização.")
        return self.api_factory(token)

    def deploy(self, request: DeploymentRequest, secrets: Mapping[str, memoryview]) -> ProviderDeployment:
        binding = self.bindings.get(request.project_id, request.tenant_id)
        if binding is None:
            raise DeploymentPolicyError("Projeto ainda não está conectado ao Railway.")
        revision = str(request.source_revision or "").strip().lower()
        if not _REVISION.fullmatch(revision):
            raise DeploymentPolicyError("Sincronize o projeto com o GitHub antes de publicar.")
        api = self._api_for(request.tenant_id)
        variable_values: dict[str, str] = {}
        try:
            for name, material in secrets.items():
                variable_values[name] = bytes(material).decode("utf-8")
            if variable_values:
                api.upsert_variables(binding.railway_project_id, binding.environment_id, binding.service_id, variable_values)
            deployment_id = api.deploy_service(binding.service_id, binding.environment_id)
        finally:
            variable_values.clear()
        _identifier(deployment_id, "Deployment")
        current = api.deployment(deployment_id)
        reported_revision = _revision_from_meta(current.get("meta"))
        if reported_revision is None:
            raise DeploymentPolicyError("O Railway ainda não confirmou a revisão aprovada pelo Olympus.")
        if not revision.startswith(reported_revision) and not reported_revision.startswith(revision):
            raise DeploymentPolicyError("O Railway iniciou uma revisão diferente da aprovada pelo Olympus.")
        status = _RAILWAY_STATUS.get(str(current.get("status") or "QUEUED").upper(), "queued")
        self._remember_deployment(deployment_id, binding)
        return ProviderDeployment("railway", deployment_id, status, _provider_url(current), revision)

    def rollback(self, deployment_id: str, target_deployment_id: str) -> ProviderDeployment:
        binding = self._deployment_binding(deployment_id)
        target_binding = self._deployment_binding(target_deployment_id)
        if binding is None or binding != target_binding:
            raise DeploymentPolicyError("Deployments não pertencem ao mesmo serviço Railway.")
        api = self._api_for(binding.tenant_id)
        target = api.deployment(target_deployment_id)
        if not target.get("canRollback"):
            raise DeploymentPolicyError("A versão selecionada não pode ser restaurada no Railway.")
        value = api.rollback(target_deployment_id)
        result_id = _identifier(str(value.get("id") or ""), "Deployment")
        self._remember_deployment(result_id, binding)
        return ProviderDeployment("railway", result_id, _RAILWAY_STATUS.get(str(value.get("status") or "QUEUED").upper(), "queued"), _provider_url(value), target_deployment_id)

    def configure_domain(self, deployment_id: str, domain: str) -> ProviderDeployment:
        binding = self._deployment_binding(deployment_id)
        if binding is None:
            raise DeploymentPolicyError("Deployment Railway não reconhecido nesta sessão.")
        api = self._api_for(binding.tenant_id)
        configured = api.create_domain(binding.railway_project_id, binding.environment_id, binding.service_id, domain)
        status_data = configured.get("status") if isinstance(configured.get("status"), dict) else {}
        records = []
        for record in status_data.get("dnsRecords") or ():
            if not isinstance(record, dict):
                continue
            records.append(ProviderDnsRecord(
                str(record.get("hostlabel") or "")[:253],
                str(record.get("requiredValue") or "")[:2048],
                str(record.get("status") or "pending")[:40].lower(),
            ))
        current = api.deployment(deployment_id)
        return ProviderDeployment(
            "railway", deployment_id,
            _RAILWAY_STATUS.get(str(current.get("status") or "QUEUED").upper(), "queued"),
            "https://" + domain, str(configured.get("id") or deployment_id),
            "pending" if records else "configured", tuple(records),
        )


class RailwayIntegrationService:
    """Tenant-scoped Railway connection and binding management."""

    def __init__(self, data_dir: Path, api_factory: Callable[[str], RailwayApi] = RailwayApi, clock=time.time) -> None:
        self.bindings = RailwayBindingStore(Path(data_dir) / "railway-bindings.json")
        self.api_factory = api_factory
        self.clock = clock
        self._tokens: dict[str, str] = {}
        self._accounts: dict[str, dict] = {}
        self._lock = RLock()

    def connect(self, tenant_id: str, token: str) -> dict:
        tenant = _identifier(tenant_id, "Organização")
        api = self.api_factory(token)
        account = api.account()
        if not account.get("id"):
            raise RailwayApiError(401, "Token do Railway sem acesso válido.")
        safe_account = {"id": str(account.get("id")), "name": str(account.get("name") or "Railway")[:200]}
        with self._lock:
            self._tokens[tenant] = str(token).strip()
            self._accounts[tenant] = safe_account
        return safe_account

    def disconnect(self, tenant_id: str) -> None:
        tenant = _identifier(tenant_id, "Organização")
        with self._lock:
            self._tokens.pop(tenant, None)
            self._accounts.pop(tenant, None)

    def token(self, tenant_id: str) -> str:
        tenant = _identifier(tenant_id, "Organização")
        with self._lock:
            return self._tokens.get(tenant, "")

    def status(self, project_id: str, tenant_id: str) -> dict:
        tenant = _identifier(tenant_id, "Organização")
        project = _identifier(project_id, "Projeto")
        with self._lock:
            account = self._accounts.get(tenant)
        return {"account": account, "binding": self.bindings.get(project, tenant)}

    def link(self, project_id: str, tenant_id: str, railway_project_id: str, service_id: str, environment_id: str, repository: str) -> RailwayBinding:
        project = _identifier(project_id, "Projeto")
        tenant = _identifier(tenant_id, "Organização")
        railway_project = _identifier(railway_project_id, "Projeto Railway")
        service = _identifier(service_id, "Serviço")
        environment = _identifier(environment_id, "Ambiente")
        repo = _repository(repository)
        api = self.api_factory(self.token(tenant))
        remote_service = api.service(service)
        if str(remote_service.get("projectId") or "") != railway_project:
            raise PermissionError("O serviço não pertence ao projeto Railway informado.")
        if not api.service_instance(service, environment).get("id"):
            raise ValueError("Ambiente Railway não encontrado para este serviço.")
        now = float(self.clock())
        previous = self.bindings.get(project, tenant)
        return self.bindings.put(RailwayBinding(tenant, project, railway_project, service, environment, repo, previous.connected_at if previous else now, now))

    def unlink(self, project_id: str, tenant_id: str) -> bool:
        return self.bindings.remove(_identifier(project_id, "Projeto"), _identifier(tenant_id, "Organização"))
