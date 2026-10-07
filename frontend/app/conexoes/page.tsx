"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import olympusVersion from "@/public/olympus-version.json";
import {
  api,
  AIProviderConnection,
  ApiError,
  ConnectionsCatalog,
  ProviderTestResult,
  ProviderQualificationResult,
  RoutingPolicy,
  SaaSOrganization,
} from "@/services/api";

const STATUS_LABEL: Record<string, string> = {
  healthy: "Conectado",
  liveness_ok: "Conectado",
  disabled: "Desativado",
  unreachable: "Indisponível",
  degraded: "Verificar configuração",
  unavailable: "Indisponível",
};

const PROVIDER_KEY_LINKS: Record<string, { label: string; href: string }> = {
  openrouter: { label: "Obter chave OpenRouter", href: "https://openrouter.ai/keys" },
  groq: { label: "Obter chave Groq", href: "https://console.groq.com/keys" },
  cerebras: { label: "Obter chave Cerebras", href: "https://cloud.cerebras.ai/platform/apikeys" },
  gemini: { label: "Obter chave Gemini", href: "https://aistudio.google.com/app/apikey" },
  mistral: { label: "Obter chave Mistral", href: "https://console.mistral.ai/api-keys/" },
  zai: { label: "Obter chave Z.AI", href: "https://z.ai/manage-apikey/apikeys" },
  cloudflare: { label: "Criar token Cloudflare", href: "https://dash.cloudflare.com/profile/api-tokens" },
  openai: { label: "Obter chave OpenAI", href: "https://platform.openai.com/api-keys" },
  kimi: { label: "Obter chave Kimi", href: "https://platform.moonshot.ai/console/api-keys" },
  opencode_zen: { label: "Obter chave OpenCode Zen", href: "https://opencode.ai/zen" },
  together: { label: "Obter chave Together AI", href: "https://api.together.ai/settings/api-keys" },
  fireworks: { label: "Obter chave Fireworks AI", href: "https://app.fireworks.ai/settings/users/api-keys" },
  ollama: { label: "Instalar Ollama", href: "https://ollama.com/download" },
};

export default function ConexoesPage() {
  const ready = useRequireAuth();
  const [catalog, setCatalog] = useState<ConnectionsCatalog | null>(null);
  const [organization, setOrganization] = useState<SaaSOrganization | null>(null);
  const [testing, setTesting] = useState("");
  const [saving, setSaving] = useState("");
  const [results, setResults] = useState<Record<string, ProviderTestResult>>({});
  const [qualification, setQualification] = useState<Record<string, ProviderQualificationResult>>({});
  const [qualifying, setQualifying] = useState("");
  const [expandedProvider, setExpandedProvider] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [policySaving, setPolicySaving] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);

  const canManage = organization?.role === "owner" || organization?.role === "admin";

  async function load(showRefresh = false) {
    if (showRefresh) setRefreshing(true);
    setError("");
    try {
      const [connections, current] = await Promise.all([api.listarConexoes(), api.obterOrganizacao()]);
      setCatalog(connections);
      setOrganization(current);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Não foi possível carregar as conexões.");
    } finally {
      if (showRefresh) setRefreshing(false);
    }
  }

  useEffect(() => { if (ready) void load(); }, [ready]);

  async function testProvider(providerId: string) {
    setTesting(providerId); setError("");
    try {
      const result = await api.testarProvedor(providerId);
      setResults((current) => ({ ...current, [providerId]: result }));
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Não foi possível testar esta conexão.");
    } finally { setTesting(""); }
  }

  async function qualifyProvider(provider: AIProviderConnection) {
    const mayCharge = provider.tier === "paid" || provider.tier === "free_paid" || provider.cost === "Pode exigir créditos" || provider.cost === "Conforme plano";
    if (mayCharge && !window.confirm("A qualificação executa probes reais e pode consumir créditos conforme seu plano. Continuar?")) return;
    setQualifying(provider.id); setError("");
    try {
      const result = await api.qualificarProvedor(provider.id, mayCharge);
      setQualification((current) => ({ ...current, [provider.id]: result }));
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Não foi possível qualificar este provedor.");
    } finally { setQualifying(""); }
  }

  async function updateProvider(providerId: string, payload: { enabled?: boolean; priority?: number; automatic?: boolean }) {
    setSaving(providerId); setError("");
    try { setCatalog(await api.atualizarProvedor(providerId, payload)); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Não foi possível atualizar esta conexão."); }
    finally { setSaving(""); }
  }

  async function saveProviderCredentials(providerId: string, values: Record<string, string>) {
    setSaving(providerId); setError("");
    try { setCatalog(await api.salvarCredenciaisProvedor(providerId, values)); }
    catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Não foi possível salvar as credenciais.");
      throw reason;
    } finally { setSaving(""); }
  }

  function updatePriorityDraft(providerId: string, value: number) {
    setCatalog((current) => current ? {
      ...current,
      providers: current.providers.map((provider) => provider.id === providerId ? { ...provider, priority: value } : provider),
    } : current);
  }

  function updatePolicyDraft(changes: Partial<RoutingPolicy>) {
    setCatalog((current) => current ? { ...current, routing_policy: { ...current.routing_policy, ...changes } } : current);
  }

  async function savePolicy() {
    if (!catalog) return;
    setPolicySaving(true); setError("");
    try { setCatalog(await api.atualizarPoliticaDeRotas(catalog.routing_policy)); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Não foi possível salvar a política de rotas."); }
    finally { setPolicySaving(false); }
  }

  if (!ready) return null;
  return <PainelShell><main className="mx-auto max-w-6xl px-5 py-10 md:px-10">
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-500/70">Central do Olympus</p><h1 className="mt-2 text-2xl font-semibold text-zinc-100">Inteligência</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">Veja rapidamente quais provedores estão disponíveis. Abra apenas o provedor que deseja configurar.</p></div>
      <div className="flex items-center gap-2"><span className="rounded-full border border-white/[0.08] px-3 py-1.5 text-[11px] text-zinc-500">OLYMPUS {olympusVersion.version}</span><span className="rounded-full border border-emerald-500/20 bg-emerald-500/[0.06] px-3 py-1.5 text-xs text-emerald-300"><span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400"/>Fallback inteligente</span></div>
    </div>
    {error && <div className="mb-5 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-300">{error}</div>}

    {catalog && <div className="mb-6 grid gap-3 sm:grid-cols-3">
      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.022] p-4"><p className="text-[11px] uppercase tracking-[0.16em] text-zinc-600">Provedores</p><p className="mt-2 text-2xl font-semibold text-zinc-100">{catalog.providers.length}</p><p className="mt-1 text-xs text-zinc-600">conexões disponíveis</p></div>
      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.022] p-4"><p className="text-[11px] uppercase tracking-[0.16em] text-zinc-600">Operacionais</p><p className="mt-2 text-2xl font-semibold text-emerald-300">{catalog.providers.filter((provider) => provider.healthy && provider.enabled).length}</p><p className="mt-1 text-xs text-zinc-600">aptos para teste/uso</p></div>
      <div className="rounded-2xl border border-white/[0.07] bg-white/[0.022] p-4"><p className="text-[11px] uppercase tracking-[0.16em] text-zinc-600">Fallback</p><p className="mt-2 text-2xl font-semibold text-cyan-300">{catalog.providers.filter((provider) => provider.automatic_active).length}</p><p className="mt-1 text-xs text-zinc-600">rotas automáticas ativas</p></div>
    </div>}

    {catalog && <section className="mb-6 rounded-2xl border border-white/[0.08] bg-white/[0.022] p-4">
      <div className="flex items-center justify-between gap-4"><div><h2 className="text-sm font-medium text-zinc-200">Política de continuidade</h2><p className="mt-1 text-xs text-zinc-600">{catalog.routing_policy.mode === "free_first" ? "Somente gratuito" : catalog.routing_policy.mode} · {catalog.routing_policy.free_attempt_limit} tentativas gratuitas · pago {catalog.routing_policy.paid_fallback_authorized ? "autorizado" : "desativado"}</p></div><button type="button" onClick={() => setPolicyOpen((value) => !value)} className="rounded-lg border border-white/[0.08] px-3 py-2 text-xs text-zinc-400">{policyOpen ? "Fechar" : "Configurar"}</button></div>
      {policyOpen && <div className="mt-4 border-t border-white/[0.06] pt-4"><div className="grid gap-4 md:grid-cols-3">
        <label className="text-xs text-zinc-500">Modo<select value={catalog.routing_policy.mode} disabled={!canManage} onChange={(event) => updatePolicyDraft({ mode: event.target.value as RoutingPolicy["mode"] })} className="mt-2 w-full rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-2.5 text-zinc-300 outline-none"><option value="free_first">Somente gratuito</option><option value="protected">Gratuito → pago autorizado</option><option value="premium_direct">Premium direto</option></select></label>
        <label className="text-xs text-zinc-500">Tentativas gratuitas<input type="number" min={1} max={8} value={catalog.routing_policy.free_attempt_limit} disabled={!canManage} onChange={(event) => updatePolicyDraft({ free_attempt_limit: Math.max(1, Math.min(8, Number(event.target.value) || 1)) })} className="mt-2 w-full rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-2.5 text-zinc-300 outline-none" /></label>
        <label className="text-xs text-zinc-500">Teto por missão (US$)<input type="number" min={0} max={1000} step="0.10" value={catalog.routing_policy.paid_spend_cap_usd} disabled={!canManage} onChange={(event) => updatePolicyDraft({ paid_spend_cap_usd: Math.max(0, Number(event.target.value) || 0), paid_fallback_authorized: Number(event.target.value) > 0 })} className="mt-2 w-full rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-2.5 text-zinc-300 outline-none" /></label>
      </div><div className="mt-4 flex justify-end"><button onClick={() => void savePolicy()} disabled={!canManage || policySaving} className="rounded-lg bg-zinc-100 px-4 py-2 text-xs font-medium text-zinc-950 disabled:bg-zinc-700 disabled:text-zinc-500">{policySaving ? "Salvando…" : "Salvar política"}</button></div></div>}
    </section>}

    <section>
      <div className="mb-4 flex items-center justify-between gap-4"><div><h2 className="font-medium text-zinc-100">Provedores</h2><p className="mt-1 text-xs text-zinc-600">Status, modelos e fallback ficam visíveis; detalhes aparecem somente ao configurar.</p></div><button onClick={() => void load(true)} disabled={refreshing} className="rounded-lg border border-white/[0.08] px-3 py-2 text-xs text-zinc-400 transition hover:bg-white/[0.04] hover:text-zinc-100 disabled:cursor-wait disabled:opacity-50">{refreshing ? "Atualizando…" : "Atualizar tudo"}</button></div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {catalog?.providers.map((provider) => <ProviderCard key={provider.id} provider={provider} canManage={Boolean(canManage)} expanded={expandedProvider === provider.id} onExpand={() => setExpandedProvider((current) => current === provider.id ? "" : provider.id)} testing={testing === provider.id} qualifying={qualifying === provider.id} saving={saving === provider.id} result={results[provider.id]} qualification={qualification[provider.id]} onTest={() => void testProvider(provider.id)} onQualify={() => void qualifyProvider(provider)} onToggle={(enabled) => void updateProvider(provider.id, { enabled })} onAutomatic={(automatic) => void updateProvider(provider.id, { automatic })} onPriority={(priority) => updatePriorityDraft(provider.id, priority)} onSavePriority={() => void updateProvider(provider.id, { priority: provider.priority })} onSaveCredentials={(values) => saveProviderCredentials(provider.id, values)}/>) }
      </div>
      {!catalog && !error && <div className="rounded-2xl border border-white/[0.07] p-8 text-center text-sm text-zinc-600">Verificando conexões…</div>}
    </section>

    {catalog?.plugins.length ? <section className="mt-8 rounded-2xl border border-white/[0.07] bg-white/[0.018] p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-medium text-zinc-200">Plugins de trabalho</h2><p className="mt-1 text-xs text-zinc-600">{catalog.plugins.length} integração(ões) disponível(is).</p></div><Link href="/projetos" className="text-xs text-cyan-300/80">Integrações por projeto →</Link></div></section> : null}
  </main></PainelShell>;
}

function ProviderCard({ provider, canManage, expanded, onExpand, testing, qualifying, saving, result, qualification, onTest, onQualify, onToggle, onAutomatic, onPriority, onSavePriority, onSaveCredentials }: {
  provider: AIProviderConnection;
  canManage: boolean;
  expanded: boolean;
  onExpand: () => void;
  testing: boolean;
  qualifying: boolean;
  saving: boolean;
  result?: ProviderTestResult;
  qualification?: ProviderQualificationResult;
  onTest: () => void;
  onQualify: () => void;
  onToggle: (enabled: boolean) => void;
  onAutomatic: (automatic: boolean) => void;
  onPriority: (priority: number) => void;
  onSavePriority: () => void;
  onSaveCredentials: (values: Record<string, string>) => Promise<void>;
}) {
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
  const [savingCredentials, setSavingCredentials] = useState(false);
  const available = provider.healthy && provider.enabled;
  const modelText = provider.model_count ? `${provider.model_count} modelos` : provider.external_gateway ? "Gateway não detectado" : provider.configured ? "Sem modelos" : "Não configurado";

  function toggleAutomatic(automatic: boolean) {
    const mayCharge = provider.tier === "paid" || provider.tier === "free_paid" || provider.cost === "Pode exigir créditos" || provider.cost === "Conforme plano";
    if (automatic && mayCharge && !window.confirm("Este provedor pode consumir créditos conforme o seu plano. Deseja incluí-lo no fallback automático?")) return;
    onAutomatic(automatic);
  }
  function runTest() {
    if ((provider.tier === "paid" || provider.tier === "free_paid") && !window.confirm("Este teste fará uma geração real e pode consumir créditos da sua conta. Continuar?")) return;
    onTest();
  }
  async function saveCredentials() {
    const values = Object.fromEntries(Object.entries(credentialValues).filter(([, value]) => value.trim()));
    if (!Object.keys(values).length) return;
    setSavingCredentials(true);
    try { await onSaveCredentials(values); setCredentialValues({}); }
    finally { setSavingCredentials(false); }
  }

  return <article className={`rounded-2xl border bg-white/[0.022] p-4 transition ${expanded ? "border-cyan-400/20" : "border-white/[0.07] hover:border-white/[0.12]"}`}>
    <button type="button" onClick={onExpand} className="w-full text-left" aria-expanded={expanded}>
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate text-sm font-medium text-zinc-100">{provider.name}</h3><p className="mt-1 truncate text-[11px] text-zinc-600">{modelText} · {provider.capacity_state || "candidate"}</p></div><span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${available ? "bg-emerald-500/[0.09] text-emerald-300" : "bg-white/[0.045] text-zinc-500"}`}><span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${available ? "bg-emerald-400" : "bg-zinc-600"}`}/>{STATUS_LABEL[provider.status] || provider.status}</span></div>
      <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-zinc-500"><span>Fallback: {provider.automatic_active ? "ativo" : "inativo"}</span><span className="text-cyan-300/80">{expanded ? "Fechar" : provider.configured ? "Configurar" : "Configurar agora"} {expanded ? "↑" : "↓"}</span></div>
    </button>

    {expanded && <div className="mt-4 border-t border-white/[0.06] pt-4">
      <p className="text-xs leading-5 text-zinc-600">{provider.description}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-[10px]"><span className="rounded-full border border-white/[0.07] px-2 py-1 text-zinc-500">ready {provider.capacity_counts?.ready || 0}</span><span className="rounded-full border border-white/[0.07] px-2 py-1 text-zinc-500">cooldown {provider.capacity_counts?.cooldown || 0}</span><span className="rounded-full border border-white/[0.07] px-2 py-1 text-zinc-500">prioridade {provider.priority}</span></div>
      {PROVIDER_KEY_LINKS[provider.id] && <a href={PROVIDER_KEY_LINKS[provider.id].href} target="_blank" rel="noreferrer" className="mt-3 inline-flex text-[11px] text-cyan-300/80 transition hover:text-cyan-200">{PROVIDER_KEY_LINKS[provider.id].label} ↗</a>}

      {Boolean(provider.credential_fields?.length) && <div className="mt-3 rounded-lg border border-white/[0.06] bg-black/10 p-3"><p className="text-[11px] text-zinc-500">{provider.configured ? "Credenciais configuradas com segurança" : "Configure os campos obrigatórios"}</p><div className="mt-2 space-y-2">{provider.credential_fields?.map((field) => <label key={field.id} className="block"><span className="mb-1 block text-[10px] text-zinc-600">{field.label}{field.required ? " *" : ""}</span><input type={field.secret ? "password" : "text"} autoComplete="off" value={credentialValues[field.id] ?? ""} onChange={(event) => setCredentialValues((current) => ({ ...current, [field.id]: event.target.value }))} placeholder={field.configured ? `${field.label} configurado — deixe vazio para manter` : field.placeholder || field.label} disabled={!canManage || savingCredentials} className="w-full rounded-lg border border-white/[0.08] bg-[#181818] px-3 py-2 text-xs text-zinc-200 outline-none"/>{field.help && <span className="mt-1 block text-[10px] leading-4 text-zinc-700">{field.help}</span>}</label>)}</div><button type="button" onClick={() => void saveCredentials()} disabled={!canManage || savingCredentials || !Object.values(credentialValues).some((value) => value.trim())} className="mt-3 rounded-lg bg-cyan-400 px-3 py-2 text-xs font-medium text-zinc-950 disabled:opacity-40">{savingCredentials ? "Salvando…" : "Salvar credenciais"}</button></div>}

      <div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11px] text-zinc-500"><span>Ativo</span><input type="checkbox" checked={provider.enabled} disabled={!canManage || !provider.configured || saving} onChange={(event) => onToggle(event.target.checked)} className="h-4 w-4 accent-cyan-400"/></label><label className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11px] text-zinc-500"><span>Fallback automático</span><input type="checkbox" checked={provider.automatic_active} disabled={!canManage || !provider.configured || !provider.enabled || saving} onChange={(event) => toggleAutomatic(event.target.checked)} className="h-4 w-4 accent-cyan-400"/></label></div>
      <div className="mt-3 flex flex-wrap gap-2"><label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-white/[0.07] px-3"><span className="text-[11px] text-zinc-600">Prioridade</span><input aria-label={`Prioridade de ${provider.name}`} type="number" min={1} max={999} value={provider.priority} disabled={!canManage || saving} onChange={(event) => onPriority(Math.max(1, Math.min(999, Number(event.target.value) || 1)))} className="w-full bg-transparent py-2 text-right text-xs text-zinc-300 outline-none"/></label><button disabled={!canManage || saving} onClick={onSavePriority} className="rounded-lg border border-white/[0.08] px-3 text-xs text-zinc-400 disabled:opacity-30">Salvar</button><button disabled={testing} onClick={runTest} className="rounded-lg bg-white/[0.07] px-3 text-xs text-zinc-300 transition hover:bg-white/[0.11] disabled:opacity-40">{testing ? "Testando…" : "Testar"}</button><button disabled={!canManage || qualifying || !provider.healthy} onClick={onQualify} className="rounded-lg border border-cyan-400/15 px-3 text-xs text-cyan-300/80 disabled:opacity-40">{qualifying ? "Qualificando…" : "Qualificar"}</button></div>
      {result && <p className={`mt-3 text-xs ${result.healthy ? "text-emerald-400" : "text-amber-300"}`}>{result.message}</p>}
      {qualification && <p className={`mt-2 text-xs ${qualification.qualified_count ? "text-emerald-400" : "text-amber-300"}`}>{qualification.qualified_count} modelo(s) qualificado(s) em {qualification.qualification_level}.</p>}
      {provider.external_gateway && !provider.healthy && <p className="mt-3 text-[11px] leading-4 text-cyan-200/60">Abra o Free Claude Code para que o Olympus detecte o gateway local.</p>}
    </div>}
  </article>;
}
