"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type SkillsFabricCatalog } from "@/services/api";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";

const LABELS: Record<string, string> = {
  "writing-plans": "Planejamento",
  "executing-plans": "Execução do plano",
  "systematic-debugging": "Diagnóstico de falhas",
  "test-driven-development": "Desenvolvimento guiado por testes",
  "requesting-code-review": "Revisão de código",
  "verification-before-completion": "Verificação antes da entrega",
};

export default function SkillsFabricPage() {
  const ready = useRequireAuth();
  const [catalog, setCatalog] = useState<SkillsFabricCatalog | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [canManage, setCanManage] = useState(false);

  async function load() {
    setBusy(true); setError("");
    try {
      const [data, organization] = await Promise.all([api.skillsFabric(), api.obterOrganizacao()]);
      setCatalog(data);
      setCanManage(organization.role === "owner" || organization.role === "admin");
    }
    catch (e) { setError(e instanceof ApiError ? e.message : "Não foi possível carregar as skills."); }
    finally { setBusy(false); }
  }
  useEffect(() => { if (ready) void load(); }, [ready]);

  async function save(values: { enabled?: boolean; disabled_skills?: string[] }) {
    if (!canManage || busy) return;
    setBusy(true); setError("");
    try { setCatalog(await api.configurarSkillsFabric(values)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Não foi possível salvar a configuração."); }
    finally { setBusy(false); }
  }

  function toggleSkill(id: string) {
    if (!catalog || busy) return;
    const disabled = new Set(catalog.disabled_skills || []);
    if (disabled.has(id)) disabled.delete(id); else disabled.add(id);
    void save({ disabled_skills: [...disabled] });
  }

  if (!ready) return null;
  return <PainelShell><main className="mx-auto max-w-5xl px-5 py-8 text-[var(--app-text)] md:px-8">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><p className="text-xs text-zinc-500">OLYMPUS 3.0.8</p><h1 className="mt-1 text-2xl font-semibold">Skills Fabric</h1></div>
      <button type="button" onClick={() => void load()} disabled={busy} className="rounded-lg border border-[var(--app-border)] px-4 py-2 text-sm disabled:opacity-40">{busy ? "Aguarde…" : "Atualizar status"}</button>
    </div>
    <p className="mt-4 max-w-2xl text-sm leading-6 text-zinc-500">Métodos de planejamento, diagnóstico e verificação para as missões de desenvolvimento do Olympus.</p>
    {error && <p role="alert" className="mt-5 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
    {!catalog && !error && <p className="mt-8 text-sm text-zinc-500">Carregando biblioteca…</p>}
    {catalog && <>
      <section className="mt-7 rounded-2xl border border-[var(--app-border)] bg-[var(--app-panel)] p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><h2 className="text-lg font-semibold">Superpowers <span className="text-zinc-500">{catalog.version ? `v${catalog.version}` : "indisponível"}</span></h2>
            <p className="mt-2 text-sm text-zinc-500">{catalog.healthy ? "Biblioteca verificada" : "Biblioteca indisponível ou com falha de integridade"} · {catalog.enabled ? "Ativada" : "Desativada"}</p></div>
          <button type="button" role="switch" aria-checked={catalog.enabled} aria-label="Ativar Superpowers" onClick={() => void save({ enabled: !catalog.enabled })} disabled={busy || !canManage || (!catalog.healthy && !catalog.enabled)} style={{ background: catalog.enabled ? "var(--app-text)" : "var(--app-panel-raised)", color: catalog.enabled ? "var(--app-bg)" : "var(--app-text)" }} className="rounded-xl px-4 py-2 text-sm disabled:opacity-40">{catalog.enabled ? "Desativar" : "Ativar"}</button>
        </div>
        <p className="mt-5 text-xs leading-5 text-zinc-500">A configuração vale para esta organização e é consultada a cada nova ação. Se uma skill ficar indisponível, a missão continua com o fluxo padrão.</p>
      </section>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {catalog.skills.filter(s => s.supported).map(skill => <section key={skill.id} className="rounded-xl border border-[var(--app-border)] bg-[var(--app-panel)] p-5">
          <div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-medium">{LABELS[skill.id] || skill.id}</h3><p className="mt-1 text-xs text-zinc-500">{skill.healthy ? (skill.enabled ? "Disponível para seleção automática" : "Desativada") : "Falha de integridade"}</p></div>
            <input type="checkbox" aria-label={LABELS[skill.id] || skill.id} checked={!(catalog.disabled_skills || []).includes(skill.id)} onChange={() => toggleSkill(skill.id)} disabled={busy || !canManage || !catalog.enabled || !skill.healthy} className="mt-1 h-4 w-4 accent-[var(--app-text)]" /></div>
        </section>)}
      </div>
      <p className="mt-6 text-sm leading-6 text-zinc-500">As skills são selecionadas conforme a tarefa e o estado da execução. O diagnóstico da missão registra a skill, sua versão, o modelo e o provedor utilizados.</p>
      <details className="mt-5 rounded-xl border border-[var(--app-border)] p-4 text-xs text-zinc-500"><summary className="cursor-pointer">Biblioteca e compatibilidade</summary>
        <p className="mt-3 leading-5">{catalog.skills.length} skills preservadas na biblioteca. Esta versão conecta seis métodos ao ciclo atual. As demais aguardam adaptação às ferramentas do Olympus.</p>
        <p className="mt-2 leading-5">As orientações entram no contexto do modelo. O ciclo atual mantém as ações permitidas e as verificações de entrega. Revisão ocorre no mesmo agente; execução paralela de subagentes ainda não está integrada.</p>
        <p className="mt-2 leading-5">Atualizações da biblioteca são entregues em pacotes versionados e validados.</p>
        {catalog.commit && <p className="mt-2 break-all">Commit: {catalog.commit}</p>}
        <a href="https://github.com/obra/superpowers" target="_blank" rel="noreferrer" className="mt-2 inline-block underline">Superpowers · licença MIT</a>
      </details>
    </>}
  </main></PainelShell>;
}
