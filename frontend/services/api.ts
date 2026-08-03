import type {
  DashboardSummary,
  Execucao,
  Log,
  LoginRequest,
  LoginResponse,
  Projeto,
} from "@/types/dashboard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

  return response.json() as Promise<T>;
}

export const api = {
  login: (payload: LoginRequest) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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
};

export { ApiError };
