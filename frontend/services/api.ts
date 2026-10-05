import type {
  DashboardSummary,
  Execucao,
  Log,
  LoginRequest,
  LoginResponse,
  Projeto,
} from "@/types/dashboard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000"
);

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("olympus_token") : null;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    if (response.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("olympus_token");
      window.dispatchEvent(new Event("olympus:unauthorized"));
    }
    throw new ApiError(response.status, detail.detail ?? "Erro ao comunicar com a API.");
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("olympus_token") : null;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: file,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    if (response.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("olympus_token");
      window.dispatchEvent(new Event("olympus:unauthorized"));
    }
    throw new ApiError(response.status, detail.detail ?? "Não foi possível enviar o arquivo.");
  }
  return response.json() as Promise<T>;
}

async function download(path: string, fallbackName: string): Promise<void> {
  const token = typeof window !== "undefined" ? localStorage.getItem("olympus_token") : null;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new ApiError(response.status, detail.detail ?? "Não foi possível baixar o resultado.");
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const matched = disposition.match(/filename="?([^";]+)"?/i);
  const fileName = matched?.[1] ?? fallbackName;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export type CloudProject = {
  project_id: string;
  name: string;
  tenant_id: string;
  created_at: number;
  updated_at: number;
};

export type CloudExecution = {
  execution_id: string;
  project_id: string;
  mission_id: string;
  task: string;
  status: string;
  created_at: number;
  updated_at: number;
  error?: string | null;
  resume_count?: number;
};

export type CloudEvent = {
  seq: number;
  event: string;
  at: number;
  [key: string]: unknown;
};

export type CloudAttachment = {
  attachment_id: string;
  project_id: string;
  name: string;
  content_type: string;
  size: number;
  kind: "text" | "document" | "image" | "archive";
  created_at: number;
};

export type CloudProjectVersion = {
  version_id: string;
  project_id: string;
  label: string;
  reason: "manual" | "pre_publish" | "mission" | "pre_restore" | string;
  created_at: number;
  file_count: number;
  size_bytes: number;
  execution_id?: string | null;
};

export type CloudVersionComparison = {
  added: string[];
  modified: string[];
  deleted: string[];
};

export type CloudPreviewSession = {
  preview_url: string;
  entrypoint: string;
  expires_at: number;
  kind: "static" | "runtime";
  status: string;
};

export type CloudStudioFile = {
  path: string;
  size: number;
  sha256: string;
  updated_at: number;
};

export type CloudStudioFileContent = CloudStudioFile & {
  content: string;
  safety_backup?: CloudProjectVersion;
};

export type CloudRuntimeStatus = {
  status: "starting" | "running" | "stopped" | "failed";
  framework?: string | null;
  preview_url?: string | null;
  error?: string | null;
  started_at?: number;
  expires_at?: number;
};

export type CloudRuntimeLog = {
  seq: number;
  at: number;
  stream: string;
  message: string;
};

export type CloudGitHubAccount = {
  login: string;
  name: string;
  avatar_url: string;
};

export type CloudGitHubRepository = {
  project_id: string;
  owner: string;
  repo: string;
  branch: string;
  html_url: string;
  private: boolean;
  auto_sync: boolean;
  last_commit_sha?: string | null;
  pages_url?: string | null;
  pages_status?: string | null;
};

export type CloudGitHubStatus = {
  connected: boolean;
  account?: CloudGitHubAccount | null;
  repository?: CloudGitHubRepository | null;
};

export type CloudGitHubSync = {
  owner: string;
  repo: string;
  branch: string;
  commit_sha: string;
  commit_url: string;
  files_changed: number;
  unchanged: boolean;
};

export type CloudGitHubCommit = {
  sha: string;
  message: string;
  author: string;
  date: string;
  html_url: string;
};

export type CloudPublication = {
  url: string;
  status: string;
  error?: string | null;
  branch?: string;
  commit_sha?: string;
  files_published?: number;
};

export type CloudRailwayBinding = {
  project_id: string;
  railway_project_id: string;
  service_id: string;
  environment_id: string;
  repository: string;
};

export type CloudDeployment = {
  provider: "railway";
  deployment_id: string;
  status: "queued" | "building" | "ready" | "failed";
  url?: string | null;
  provider_reference?: string | null;
  domain_status?: "pending" | "configured" | "failed" | null;
  dns_records?: { host: string; value: string; status: string }[];
};

export type CloudRailwayStatus = {
  connected: boolean;
  account?: { id: string; name: string } | null;
  binding?: CloudRailwayBinding | null;
  deployments: CloudDeployment[];
};

export type CloudSecretReference = {
  name: string;
  environment: "preview" | "production";
  version: number;
  updated_at: number;
};

export type SaaSOrganization = {
  organization_id: string;
  name: string;
  slug: string;
  owner_user_id: string;
  plan_id: string;
  subscription_status: string;
  created_at: number;
  role?: "owner" | "admin" | "builder" | "viewer";
};

export type SaaSMember = {
  organization_id: string;
  user_id: string;
  email: string;
  role: "owner" | "admin" | "builder" | "viewer";
  status: string;
  joined_at: number;
};

export type SaaSUsage = {
  period: string;
  usage: Record<string, number>;
  plan_id: string;
  subscription_status: string;
  limits: Record<string, number>;
};

export type SaaSAuditEvent = {
  sequence: number;
  action: string;
  actor_user_id: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown>;
  created_at: number;
  event_hash: string;
};

export type ProviderCredentialField = {
  id: string;
  label: string;
  secret: boolean;
  required: boolean;
  configured: boolean;
  placeholder?: string;
  help?: string;
};

export type AIProviderConnection = {
  id: string;
  name: string;
  description: string;
  cost: string;
  tier: "free" | "local" | "paid" | "free_paid";
  configured: boolean;
  enabled: boolean;
  priority: number;
  healthy: boolean;
  status: string;
  automatic_active: boolean;
  model_count: number;
  models: string[];
  safe_free_model_count?: number | null;
  external_gateway?: boolean;
  capacity_state?: string;
  capacity_counts?: Record<string, number>;
  capacity_cooldown_until?: number;
  credential_fields?: ProviderCredentialField[];
};

export type RoutingPolicy = {
  mode: "free_first" | "protected" | "premium_direct";
  free_attempt_limit: number;
  paid_fallback_authorized: boolean;
  paid_attempt_limit: number;
  paid_spend_cap_usd: number;
};

export type OlympusPlugin = {
  id: string;
  name: string;
  description: string;
};

export type ConnectionsCatalog = {
  providers: AIProviderConnection[];
  plugins: OlympusPlugin[];
  automatic_failover: boolean;
  routing_policy: RoutingPolicy;
  capacity_fabric?: { counts: Record<string, number>; updated_at: number };
};

export type OlympusSkill = {
  id: string;
  name: string;
  version: string;
  description: string;
  source: "builtin" | "external" | string;
  category: string;
  status: "active" | "review_required" | "blocked" | string;
  source_url: string;
  license: string;
  allowed_actions: string[];
  completion_checks: string[];
  guidance: string[];
  constraints: string[];
};

export type SkillsCatalog = {
  skills: OlympusSkill[];
  counts: { active: number; review_required: number; blocked: number };
  import_policy: { source: string; automatic_execution: boolean; review_required: boolean };
};

export type ProviderQualificationResult = {
  provider: string;
  qualification_level: string;
  qualified_count: number;
  models: Array<{
    provider: string;
    model: string;
    route_id: string;
    qualified: boolean;
    probes: Array<{ probe: string; ok: boolean; latency_ms: number; error?: string | null }>;
  }>;
};

export type ProviderTestResult = {
  id: string;
  connected: boolean;
  inference_ready: boolean;
  healthy: boolean;
  status: string;
  model_count: number;
  model?: string | null;
  error?: string | null;
  message: string;
};

export type SkillsFabricCatalog = {
  name: string; version: string | null; commit?: string; enabled: boolean;
  healthy: boolean; error?: string; disabled_skills?: string[];
  skills: { id: string; supported: boolean; healthy: boolean; enabled: boolean }[];
};

export const api = {
  skillsFabric: () => request<SkillsFabricCatalog>("/skills-fabric"),
  configurarSkillsFabric: (values: { enabled?: boolean; disabled_skills?: string[] }) =>
    request<SkillsFabricCatalog>("/skills-fabric", { method: "PATCH", body: JSON.stringify(values) }),
  login: (payload: LoginRequest) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  obterOrganizacao: () => request<SaaSOrganization>("/cloud/saas/organization"),

  listarOrganizacoes: async () => {
    const data = await request<{ organizations: SaaSOrganization[] }>("/cloud/saas/organizations");
    return data.organizations;
  },

  criarOrganizacao: (name: string) =>
    request<SaaSOrganization>("/cloud/saas/organizations", { method: "POST", body: JSON.stringify({ name }) }),

  trocarOrganizacao: async (organizationId: string) => {
    const data = await request<LoginResponse>("/cloud/saas/organizations/switch", {
      method: "POST", body: JSON.stringify({ organization_id: organizationId }),
    });
    localStorage.setItem("olympus_token", data.access_token);
    return data;
  },

  listarMembros: async () => {
    const data = await request<{ members: SaaSMember[] }>("/cloud/saas/members");
    return data.members;
  },

  convidarMembro: (email: string, role: "admin" | "builder" | "viewer") =>
    request<{ invitation_token: string; expires_at: number }>("/cloud/saas/invitations", {
      method: "POST", body: JSON.stringify({ email, role }),
    }),

  aceitarConvite: (token: string, email: string, password: string) =>
    request<LoginResponse & { organization_id: string }>("/cloud/saas/invitations/accept", {
      method: "POST", body: JSON.stringify({ token, email, password }),
    }),

  alterarPapelMembro: (userId: string, role: "admin" | "builder" | "viewer") =>
    request<SaaSMember>(`/cloud/saas/members/${encodeURIComponent(userId)}`, {
      method: "PATCH", body: JSON.stringify({ role }),
    }),

  removerMembro: (userId: string) =>
    request<void>(`/cloud/saas/members/${encodeURIComponent(userId)}`, { method: "DELETE" }),

  obterUso: () => request<SaaSUsage>("/cloud/saas/usage"),

  listarConexoes: () => request<ConnectionsCatalog>(`/providers/catalog?ts=${Date.now()}`, {
    cache: "no-store",
  }),

  atualizarProvedor: (providerId: string, payload: { enabled?: boolean; priority?: number; automatic?: boolean }) =>
    request<ConnectionsCatalog>(`/providers/${encodeURIComponent(providerId)}`, {
      method: "PATCH", body: JSON.stringify(payload),
    }),

  salvarChaveProvedor: (providerId: string, secret: string) =>
    request<ConnectionsCatalog>(`/providers/${encodeURIComponent(providerId)}/credential`, {
      method: "PUT", body: JSON.stringify({ secret }),
    }),

  salvarCredenciaisProvedor: (providerId: string, values: Record<string, string>) =>
    request<ConnectionsCatalog>(`/providers/${encodeURIComponent(providerId)}/credentials`, {
      method: "PUT", body: JSON.stringify({ values }),
    }),

  removerChaveProvedor: (providerId: string) =>
    request<void>(`/providers/${encodeURIComponent(providerId)}/credential`, { method: "DELETE" }),

  atualizarPoliticaDeRotas: (payload: RoutingPolicy) =>
    request<ConnectionsCatalog>("/providers/routing-policy", {
      method: "PUT", body: JSON.stringify(payload),
    }),

  listarSkills: () => request<SkillsCatalog>("/skills"),

  importarSkillGitHub: (url: string) =>
    request<{ imported: string[]; status: string; findings: string[]; message: string }>("/skills/imports/github", {
      method: "POST", body: JSON.stringify({ url }),
    }),

  aprovarSkill: (skillId: string) =>
    request<OlympusSkill>(`/skills/${encodeURIComponent(skillId)}/approve`, {
      method: "POST", body: JSON.stringify({}),
    }),

  desativarSkill: (skillId: string) =>
    request<OlympusSkill>(`/skills/${encodeURIComponent(skillId)}`, {
      method: "PATCH", body: JSON.stringify({ status: "disabled" }),
    }),

  testarProvedor: (providerId: string) =>
    request<ProviderTestResult>(`/providers/${encodeURIComponent(providerId)}/test`, {
      method: "POST", body: JSON.stringify({}),
    }),

  qualificarProvedor: (providerId: string, allowMetered = false) =>
    request<ProviderQualificationResult>(`/providers/${encodeURIComponent(providerId)}/qualify`, {
      method: "POST", body: JSON.stringify({ max_models: 3, allow_metered: allowMetered }),
    }),

  listarAuditoria: async () => {
    const data = await request<{ events: SaaSAuditEvent[]; chain_valid: boolean }>("/cloud/saas/audit?limit=100");
    return data;
  },

  dashboardSummary: () => request<DashboardSummary>("/dashboard/summary"),

  listarProjetos: (limit = 50) => request<Projeto[]>(`/projects?limit=${limit}`),

  obterProjeto: (id: string) => request<Projeto>(`/projects/${id}`),

  execucoesDoProjeto: (id: string, limit = 50) =>
    request<Execucao[]>(`/projects/${id}/executions?limit=${limit}`),

  logsDoProjeto: (id: string, limit = 50) =>
    request<Log[]>(`/projects/${id}/logs?limit=${limit}`),

  listarExecucoes: (params: { limit?: number; project_id?: string; status?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.project_id) qs.set("project_id", params.project_id);
    if (params.status) qs.set("status", params.status);
    return request<Execucao[]>(`/executions?${qs.toString()}`);
  },

  obterExecucao: (id: string) => request<Execucao>(`/executions/${id}`),

  listarLogs: (
    params: { limit?: number; project_id?: string; execution_id?: string; level?: string } = {}
  ) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.project_id) qs.set("project_id", params.project_id);
    if (params.execution_id) qs.set("execution_id", params.execution_id);
    if (params.level) qs.set("level", params.level);
    return request<Log[]>(`/logs?${qs.toString()}`);
  },

  buscarLogs: (q: string, limit = 50) =>
    request<Log[]>(`/logs/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  listarCloudProjetos: async () => {
    const data = await request<{ projects: CloudProject[] }>('/cloud/projects');
    return data.projects;
  },

  criarCloudProjeto: (payload: { name: string; project_id?: string }) =>
    request<CloudProject>('/cloud/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  renomearCloudProjeto: (projectId: string, name: string) =>
    request<CloudProject>(`/cloud/projects/${encodeURIComponent(projectId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  excluirCloudProjeto: (projectId: string) =>
    request<void>(`/cloud/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' }),

  criarCloudMissao: (payload: { project_id: string; task: string; max_iterations?: number; attachment_ids?: string[]; routing_mode?: "free_first" | "protected" | "premium_direct"; paid_fallback_authorized?: boolean; paid_spend_cap_usd?: number; free_attempt_limit?: number }) =>
    request<CloudExecution>('/cloud/missions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  obterCloudExecucao: (id: string) =>
    request<CloudExecution>(`/cloud/executions/${id}`),

  listarCloudExecucoes: async (params: { limit?: number; project_id?: string; status?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.limit) query.set("limit", String(params.limit));
    if (params.project_id) query.set("project_id", params.project_id);
    if (params.status) query.set("status", params.status);
    const data = await request<{ executions: CloudExecution[] }>(`/cloud/executions?${query.toString()}`);
    return data.executions;
  },

  listarCloudEventos: (id: string, after = 0) =>
    request<{ execution_id: string; events: CloudEvent[] }>(`/cloud/executions/${id}/events?after=${after}`),

  cancelarCloudExecucao: (id: string) =>
    request<CloudExecution>(`/cloud/executions/${id}/cancel`, { method: 'POST', body: JSON.stringify({}) }),

  retomarCloudExecucao: (id: string) =>
    request<CloudExecution>(`/cloud/executions/${id}/resume`, { method: 'POST', body: JSON.stringify({}) }),

  enviarCloudAnexo: (projectId: string, file: File) =>
    upload<CloudAttachment>(`/cloud/projects/${encodeURIComponent(projectId)}/attachments?filename=${encodeURIComponent(file.name)}`, file),

  listarCloudAnexos: async (projectId: string) => {
    const data = await request<{ attachments: CloudAttachment[] }>(`/cloud/projects/${encodeURIComponent(projectId)}/attachments`);
    return data.attachments;
  },

  removerCloudAnexo: (projectId: string, attachmentId: string) =>
    request<void>(`/cloud/projects/${encodeURIComponent(projectId)}/attachments/${encodeURIComponent(attachmentId)}`, { method: 'DELETE' }),

  listarCloudVersoes: async (projectId: string) => {
    const data = await request<{ versions: CloudProjectVersion[] }>(`/cloud/projects/${encodeURIComponent(projectId)}/versions`);
    return data.versions;
  },

  criarCloudVersao: (projectId: string, label?: string) =>
    request<CloudProjectVersion>(`/cloud/projects/${encodeURIComponent(projectId)}/versions`, {
      method: 'POST',
      body: JSON.stringify({ label: label || null }),
    }),

  compararCloudVersao: (projectId: string, versionId: string) =>
    request<CloudVersionComparison>(`/cloud/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/compare`),

  restaurarCloudVersao: (projectId: string, versionId: string) =>
    request<{ restored: CloudProjectVersion; safety_backup: CloudProjectVersion }>(`/cloud/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/restore`, {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    }),

  criarCloudPreview: async (projectId: string) => {
    const data = await request<CloudPreviewSession>(`/cloud/projects/${encodeURIComponent(projectId)}/preview-session`, { method: 'POST', body: JSON.stringify({}) });
    return { ...data, preview_url: new URL(data.preview_url, API_BASE_URL).toString() };
  },

  listarCloudArquivos: async (projectId: string) => {
    const data = await request<{ files: CloudStudioFile[] }>(`/cloud/projects/${encodeURIComponent(projectId)}/files`);
    return data.files;
  },

  abrirCloudArquivo: (projectId: string, path: string) =>
    request<CloudStudioFileContent>(`/cloud/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`),

  salvarCloudArquivo: (projectId: string, path: string, content: string, expectedSha256: string) =>
    request<CloudStudioFileContent>(`/cloud/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`, {
      method: "PUT",
      body: JSON.stringify({ content, expected_sha256: expectedSha256 }),
    }),

  obterCloudRuntime: (projectId: string) =>
    request<CloudRuntimeStatus>(`/cloud/projects/${encodeURIComponent(projectId)}/runtime`),

  listarCloudRuntimeLogs: async (projectId: string, after = 0) => {
    const data = await request<{ logs: CloudRuntimeLog[] }>(`/cloud/projects/${encodeURIComponent(projectId)}/runtime/logs?after=${after}`);
    return data.logs;
  },

  pararCloudRuntime: (projectId: string) =>
    request<void>(`/cloud/projects/${encodeURIComponent(projectId)}/runtime`, { method: "DELETE" }),

  obterGitHubProjeto: (projectId: string) =>
    request<CloudGitHubStatus>(`/cloud/github/projects/${encodeURIComponent(projectId)}`),

  conectarGitHub: (token: string) =>
    request<{ connected: boolean; account: CloudGitHubAccount }>("/cloud/github/connection", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  desconectarGitHub: () =>
    request<void>("/cloud/github/connection", { method: "DELETE" }),

  criarGitHubRepositorio: (projectId: string, repo: string, isPrivate = false) =>
    request<CloudGitHubRepository>("/cloud/github/repositories", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, repo, private: isPrivate }),
    }),

  vincularGitHubRepositorio: (projectId: string, owner: string, repo: string, branch?: string) =>
    request<CloudGitHubRepository>(`/cloud/github/projects/${encodeURIComponent(projectId)}/repository`, {
      method: "PUT",
      body: JSON.stringify({ owner, repo, branch: branch || null }),
    }),

  desvincularGitHubRepositorio: (projectId: string) =>
    request<void>(`/cloud/github/projects/${encodeURIComponent(projectId)}/repository`, { method: "DELETE" }),

  criarGitHubBranch: (projectId: string, branch: string) =>
    request<CloudGitHubRepository>(`/cloud/github/projects/${encodeURIComponent(projectId)}/branches`, {
      method: "POST",
      body: JSON.stringify({ branch }),
    }),

  sincronizarGitHub: (projectId: string, message = "Atualização pelo Olympus") =>
    request<CloudGitHubSync>(`/cloud/github/projects/${encodeURIComponent(projectId)}/sync`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  listarGitHubCommits: async (projectId: string) => {
    const data = await request<{ commits: CloudGitHubCommit[] }>(`/cloud/github/projects/${encodeURIComponent(projectId)}/commits`);
    return data.commits;
  },

  publicarGitHubPages: (projectId: string) =>
    request<CloudPublication>(`/cloud/github/projects/${encodeURIComponent(projectId)}/publish`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  obterPublicacaoGitHub: (projectId: string) =>
    request<CloudPublication | null>(`/cloud/github/projects/${encodeURIComponent(projectId)}/publication`),

  obterRailwayProjeto: (projectId: string) =>
    request<CloudRailwayStatus>(`/cloud/railway/projects/${encodeURIComponent(projectId)}`),

  conectarRailway: (token: string) =>
    request<{ connected: boolean; account: { id: string; name: string } }>("/cloud/railway/connection", {
      method: "POST", body: JSON.stringify({ token }),
    }),

  desconectarRailway: () => request<void>("/cloud/railway/connection", { method: "DELETE" }),

  vincularRailway: (projectId: string, railwayProjectId: string, serviceId: string, environmentId: string, repository: string) =>
    request<CloudRailwayBinding>(`/cloud/railway/projects/${encodeURIComponent(projectId)}/service`, {
      method: "PUT", body: JSON.stringify({ railway_project_id: railwayProjectId, service_id: serviceId, environment_id: environmentId, repository }),
    }),

  listarRailwaySegredos: async (projectId: string) => {
    const data = await request<{ secrets: CloudSecretReference[] }>(`/cloud/railway/projects/${encodeURIComponent(projectId)}/secrets`);
    return data.secrets;
  },

  salvarRailwaySegredo: (projectId: string, name: string, value: string) =>
    request<CloudSecretReference>(`/cloud/railway/projects/${encodeURIComponent(projectId)}/secrets/${encodeURIComponent(name)}`, {
      method: "PUT", body: JSON.stringify({ value }),
    }),

  publicarRailway: (projectId: string, domain?: string) =>
    request<CloudDeployment>(`/cloud/railway/projects/${encodeURIComponent(projectId)}/deployments`, {
      method: "POST", body: JSON.stringify({ environment: "production", domain: domain || null }),
    }),

  restaurarRailway: (projectId: string, deploymentId: string, targetDeploymentId: string) =>
    request<CloudDeployment>(`/cloud/railway/projects/${encodeURIComponent(projectId)}/rollback`, {
      method: "POST", body: JSON.stringify({ deployment_id: deploymentId, target_deployment_id: targetDeploymentId, environment: "production" }),
    }),

  baixarCloudProjeto: (id: string) =>
    download(`/cloud/projects/${encodeURIComponent(id)}/download`, "resultado-olympus.zip"),
};

export { ApiError };
