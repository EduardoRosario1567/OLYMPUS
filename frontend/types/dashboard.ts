export interface LoginRequest {
  email: string;
  senha: string;
  lembrar?: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface DashboardSummary {
  total_execucoes: number;
  total_modelos: number;
  total_projetos: number;
  custo_total: number;
  latencia_media_ms: number;
  taxa_sucesso: number;
  fallback_rate: number;
  total_decisoes: number;
  modelo_mais_usado: string | null;
  agentes_implementado: boolean;
}

export interface Projeto {
  id: string;
  name: string;
  description: string | null;
  product_type: string | null;
  complexity: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Execucao {
  id: string;
  project_id: string;
  status: string;
  total_cost: number;
  total_latency_ms: number;
  success_count: number;
  fallback_count: number;
  created_at: string;
  modelo_principal: string | null;
  confianca_media: number | null;
  fallback_usado: boolean | null;
}

export interface Log {
  id: string;
  project_id: string | null;
  execution_id: string | null;
  decision_record_id: string | null;
  level: string;
  event_type: string;
  message: string;
  metadata: Record<string, unknown> | string;
  created_at: string;
}
