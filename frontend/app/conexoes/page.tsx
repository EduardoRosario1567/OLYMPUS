"use client";

import Link from "next/link";
import olympusVersion from "@/public/olympus-version.json";
import { useEffect, useState } from "react";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
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
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "available" | "attention">("all");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [notice, setNotice] = useState("");

  const canManage = organization?.role === "owner" || organization?.role === "admin";

  async function load(showRefresh = false) {
    if (showRefresh) setRefreshing(true);
    setError("");
    try {
      const [connections, current] = await Promise.all([api.listarConexoes(), api.obterOrganizacao()]);
      setCatalog(connections);
      setOrganization(current);
      setUpdatedAt(new Date());
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
    setSaving(providerId); setError(""); setNotice("");
    try { setCatalog(await api.salvarCredenciaisProvedor(providerId, values)); setNotice("Credenciais salvas. Campos deixados vazios foram mantidos."); }
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

  const providers = catalog?.providers ?? [];
  const availableCount = providers.filter((provider) => provider.enabled && provider.healthy).length;
  const modelCount = providers.reduce((total, provider) => total + (provider.model_count || 0), 0);
  const qualifiedCount = providers.reduce((total, provider) => total + (provider.capacity_counts?.ready || 0), 0);
  const visibleProviders = providers.filter((provider) => {
    const matchesQuery = `${provider.name} ${provider.id} ${provider.description}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
    const available = provider.enabled && provider.healthy;
    return matchesQuery && (filter === "all" || (filter === "available" ? available : !available));
  });

  if (!ready) return null;
  return <PainelShell><main className="connections-page mx-auto w-full max-w-6xl px-5 py-8 md:px-10 md:py-10">
    <header className="mb-7 flex flex-wrap items-start justify-between gap-5">
      <div><p className="connection-muted text-xs font-semibold uppercase tracking-[0.16em]">Central de inteligência</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">APIs e provedores</h1><p className="connection-muted mt-3 max-w-2xl text-sm leading-6">Conecte seus modelos, acompanhe a disponibilidade e defina como o OLYMPUS mantém suas missões em andamento.</p></div>
      <div className="flex flex-col items-end gap-2"><span className="connection-filter rounded-full px-3 py-1.5 text-xs">OLYMPUS {olympusVersion.version}</span><button type="button" onClick={() => void load(true)} disabled={refreshing} className="connection-filter min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:cursor-wait disabled:opacity-50">{refreshing ? "Atualizando…" : "Atualizar conexões"}</button>{updatedAt && <p className="connection-muted text-xs">Atualizado às {updatedAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</p>}</div>
    </header>
    {error && <div role="alert" className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}{!catalog && <button type="button" onClick={() => void load(true)} disabled={refreshing} className="ml-3 underline">Tentar novamente</button>}</div>}
    {notice && <p role="status" className="mb-5 rounded-xl border border-emerald-500/25 px-4 py-3 text-sm">{notice}</p>}
    {catalog && <section aria-label="Resumo das conexões" className="mb-6 grid gap-3 sm:grid-cols-3">
      {[{ label: "Conexões disponíveis", value: availableCount, detail: `${providers.length} provedores cadastrados` }, { label: "Modelos catalogados", value: modelCount, detail: "Modelos informados pelos provedores" }, { label: "Capacidade qualificada", value: qualifiedCount, detail: "Modelos prontos após qualificação" }].map((item) => <div key={item.label} className="connection-panel px-5 py-4"><p className="connection-muted text-xs font-medium">{item.label}</p><p className="mt-2 text-3xl font-semibold tabular-nums">{item.value}</p><p className="connection-muted mt-2 text-xs leading-5">{item.detail}</p></div>)}
    </section>}
    {catalog && <section className="connection-panel connection-policy mb-6 p-5">
      <div className="flex items-center justify-between gap-4"><div><h2 className="text-sm font-medium text-zinc-200">Política de continuidade</h2><p className="mt-1 text-xs text-zinc-600">{catalog.routing_policy.mode === "free_first" ? "Somente gratuito" : catalog.routing_policy.mode === "protected" ? "Gratuito → pago autorizado" : "Premium direto"} · {catalog.routing_policy.free_attempt_limit} tentativas gratuitas · pago {catalog.routing_policy.paid_fallback_authorized ? "autorizado" : "desativado"}</p></div><button type="button" onClick={() => setPolicyOpen((value) => !value)} aria-expanded={policyOpen} aria-controls="routing-policy-fields" className="rounded-lg border border-white/[0.08] px-3 py-2 text-xs text-zinc-400">{policyOpen ? "Fechar" : "Configurar"}</button></div>
      {policyOpen && <div id="routing-policy-fields" className="mt-4 border-t border-white/[0.06] pt-4"><div className="grid gap-4 md:grid-cols-3">
        <label className="text-xs text-zinc-500">Modo<select value={catalog.routing_policy.mode} disabled={!canManage} onChange={(event) => updatePolicyDraft({ mode: event.target.value as RoutingPolicy["mode"] })} className="mt-2 w-full rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-2.5 text-zinc-300 outline-none"><option value="free_first">Somente gratuito</option><option value="protected">Gratuito → pago autorizado</option><option value="premium_direct">Premium direto</option></select></label>
        <label className="text-xs text-zinc-500">Tentativas gratuitas<input type="number" min={1} max={8} value={catalog.routing_policy.free_attempt_limit} disabled={!canManage} onChange={(event) => updatePolicyDraft({ free_attempt_limit: Math.max(1, Math.min(8, Number(event.target.value) || 1)) })} className="mt-2 w-full rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-2.5 text-zinc-300 outline-none" /></label>
        <label className="text-xs text-zinc-500">Teto por missão (US$)<input type="number" min={0} max={1000} step="0.10" value={catalog.routing_policy.paid_spend_cap_usd} disabled={!canManage} onChange={(event) => updatePolicyDraft({ paid_spend_cap_usd: Math.max(0, Number(event.target.value) || 0), paid_fallback_authorized: Number(event.target.value) > 0 })} className="mt-2 w-full rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-2.5 text-zinc-300 outline-none" /></label>
      </div><div className="mt-4 flex justify-end"><button onClick={() => void savePolicy()} disabled={!canManage || policySaving} className="rounded-lg bg-zinc-100 px-4 py-2 text-xs font-medium text-zinc-950 disabled:bg-zinc-700 disabled:text-zinc-500">{policySaving ? "Salvando…" : "Salvar política"}</button></div></div>}
    </section>}

    <section>
      <div className="mb-4"><h2 className="text-lg font-semibold">Seus provedores</h2><p className="connection-muted mt-1 text-sm">Disponibilidade de conexão e qualificação de modelos são verificações diferentes.</p></div>
      {catalog && <div className="connection-toolbar mb-5 flex flex-wrap items-center justify-between gap-3">
        <label className="w-full sm:max-w-sm"><span className="sr-only">Buscar provedor</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por nome ou provedor" className="min-h-11 w-full rounded-xl px-4 py-2.5 text-sm" /></label>
        <div role="group" aria-label="Filtrar provedores" className="flex flex-wrap gap-2">{([{ value: "all", label: "Todos" }, { value: "available", label: "Disponíveis" }, { value: "attention", label: "Precisam de atenção" }] as const).map((item) => <button key={item.value} type="button" aria-pressed={filter === item.value} onClick={() => setFilter(item.value)} className="connection-filter min-h-11 rounded-xl px-3 py-2 text-xs font-medium">{item.label}</button>)}</div>
        <p role="status" className="connection-muted w-full text-xs">{visibleProviders.length} de {providers.length} provedores</p>
      </div>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {visibleProviders.map((provider) => <ProviderCard key={provider.id} provider={provider} canManage={Boolean(canManage)} expanded={expandedProvider === provider.id} onExpand={() => setExpandedProvider((current) => current === provider.id ? "" : provider.id)} testing={testing === provider.id} qualifying={qualifying === provider.id} saving={saving === provider.id} result={results[provider.id]} qualification={qualification[provider.id]} onTest={() => void testProvider(provider.id)} onQualify={() => void qualifyProvider(provider)} onToggle={(enabled) => void updateProvider(provider.id, { enabled })} onAutomatic={(automatic) => void updateProvider(provider.id, { automatic })} onPriority={(priority) => updatePriorityDraft(provider.id, priority)} onSavePriority={() => void updateProvider(provider.id, { priority: provider.priority })} onSaveCredentials={(values) => saveProviderCredentials(provider.id, values)}/>) }
      </div>
      {catalog && !visibleProviders.length && <div className="connection-panel p-8 text-center"><h3 className="font-medium">{providers.length ? "Nenhum provedor encontrado" : "Nenhum provedor cadastrado"}</h3><p className="connection-muted mt-2 text-sm">{providers.length ? "Ajuste a busca ou escolha outro filtro." : "Atualize as conexões para consultar os provedores disponíveis."}</p>{providers.length > 0 && <button type="button" onClick={() => { setQuery(""); setFilter("all"); }} className="connection-filter mt-4 min-h-11 rounded-xl px-4 py-2 text-sm">Limpar filtros</button>}</div>}
      {!catalog && !error && <div role="status" className="rounded-2xl border border-white/[0.07] p-8 text-center text-sm text-zinc-600">Verificando conexões…</div>}
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
    catch { /* Parent reports the error; keep the draft for retry. */ }
    finally { setSavingCredentials(false); }
  }

  return <article className={`provider-card self-start rounded-2xl p-5 ${expanded ? "is-expanded" : ""}`}>
    <button type="button" onClick={onExpand} className="w-full text-left" aria-expanded={expanded} aria-controls={`provider-details-${provider.id}`}>
      <div className="flex items-start gap-3"><span aria-hidden="true" className="provider-emblem">{provider.name.slice(0, 2).toUpperCase()}</span><div className="min-w-0 flex-1"><h3 className="truncate text-sm font-medium text-zinc-100">{provider.name}</h3><p className="mt-1 truncate text-[11px] text-zinc-600">{modelText}</p></div><span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${available ? "bg-emerald-500/[0.09] text-emerald-300" : "bg-white/[0.045] text-zinc-500"}`}><span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${available ? "bg-emerald-400" : "bg-zinc-600"}`}/>{!provider.enabled ? "Desativado" : STATUS_LABEL[provider.status] || "Não verificado"}</span></div>
      <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-zinc-500"><span>Fallback: {provider.automatic_active ? "ativo" : "inativo"}</span><span className="text-cyan-300/80">{expanded ? "Fechar" : provider.configured ? "Configurar" : "Configurar agora"} {expanded ? "↑" : "↓"}</span></div>
    </button>

    {expanded && <div id={`provider-details-${provider.id}`} className="mt-4 border-t border-white/[0.06] pt-4">
      <p className="text-xs leading-5 text-zinc-600">{provider.description}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-[10px]"><span className="rounded-full border border-white/[0.07] px-2 py-1 text-zinc-500">Prontos: {provider.capacity_counts?.ready || 0}</span><span className="rounded-full border border-white/[0.07] px-2 py-1 text-zinc-500">Em espera: {provider.capacity_counts?.cooldown || 0}</span><span className="rounded-full border border-white/[0.07] px-2 py-1 text-zinc-500">prioridade {provider.priority}</span></div>
      {PROVIDER_KEY_LINKS[provider.id] && <a href={PROVIDER_KEY_LINKS[provider.id].href} target="_blank" rel="noreferrer" className="mt-3 inline-flex text-[11px] text-cyan-300/80 transition hover:text-cyan-200">{PROVIDER_KEY_LINKS[provider.id].label} ↗</a>}

      {Boolean(provider.credential_fields?.length) && <div className="mt-3 rounded-lg border border-white/[0.06] bg-black/10 p-3"><p className="text-[11px] text-zinc-500">{provider.configured ? "Credenciais configuradas com segurança" : "Configure os campos obrigatórios"}</p><div className="mt-2 space-y-2">{provider.credential_fields?.map((field) => <label key={field.id} className="block"><span className="mb-1 block text-[10px] text-zinc-600">{field.label}{field.required ? " *" : ""}</span><input type={field.secret ? "password" : "text"} autoComplete="off" value={credentialValues[field.id] ?? ""} onChange={(event) => setCredentialValues((current) => ({ ...current, [field.id]: event.target.value }))} placeholder={field.configured ? `${field.label} configurado — deixe vazio para manter` : field.placeholder || field.label} disabled={!canManage || savingCredentials} className="w-full rounded-lg border border-white/[0.08] bg-[#181818] px-3 py-2 text-xs text-zinc-200 outline-none"/>{field.help && <span className="mt-1 block text-[10px] leading-4 text-zinc-700">{field.help}</span>}</label>)}</div><button type="button" onClick={() => void saveCredentials()} disabled={!canManage || savingCredentials || !Object.values(credentialValues).some((value) => value.trim())} className="mt-3 rounded-lg bg-cyan-400 px-3 py-2 text-xs font-medium text-zinc-950 disabled:opacity-40">{savingCredentials ? "Salvando…" : "Salvar credenciais"}</button></div>}

      <div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11px] text-zinc-500"><span>Ativo</span><input type="checkbox" checked={provider.enabled} disabled={!canManage || !provider.configured || saving} onChange={(event) => onToggle(event.target.checked)} className="h-4 w-4 accent-cyan-400"/></label><label className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2 text-[11px] text-zinc-500"><span>Fallback automático</span><input type="checkbox" checked={provider.automatic_active} disabled={!canManage || !provider.configured || !provider.enabled || saving} onChange={(event) => toggleAutomatic(event.target.checked)} className="h-4 w-4 accent-cyan-400"/></label></div>
      <div className="mt-3 flex flex-wrap gap-2"><label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-white/[0.07] px-3"><span className="text-[11px] text-zinc-600">Prioridade</span><input aria-label={`Prioridade de ${provider.name}`} type="number" min={1} max={999} value={provider.priority} disabled={!canManage || saving} onChange={(event) => onPriority(Math.max(1, Math.min(999, Number(event.target.value) || 1)))} className="w-full bg-transparent py-2 text-right text-xs text-zinc-300 outline-none"/></label><button disabled={!canManage || saving} onClick={onSavePriority} className="min-h-11 rounded-lg border border-white/[0.08] px-3 text-xs text-zinc-400 disabled:opacity-30">Salvar</button><button disabled={testing} onClick={runTest} className="min-h-11 rounded-lg bg-white/[0.07] px-3 text-xs text-zinc-300 transition hover:bg-white/[0.11] disabled:opacity-40">{testing ? "Testando…" : "Testar"}</button><button disabled={!canManage || qualifying || !provider.healthy} onClick={onQualify} className="min-h-11 rounded-lg border border-cyan-400/15 px-3 text-xs text-cyan-300/80 disabled:opacity-40">{qualifying ? "Qualificando…" : "Qualificar"}</button></div>
      {result && <p className={`mt-3 text-xs ${result.healthy ? "text-emerald-400" : "text-amber-300"}`}>{result.message}</p>}
      {qualification && <p className={`mt-2 text-xs ${qualification.qualified_count ? "text-emerald-400" : "text-amber-300"}`}>{qualification.qualified_count} modelo(s) qualificado(s) em {qualification.qualification_level}.</p>}
      {provider.external_gateway && !provider.healthy && <p className="mt-3 text-[11px] leading-4 text-cyan-200/60">Abra o Free Claude Code para que o Olympus detecte o gateway local.</p>}
    </div>}
  </article>;
}
