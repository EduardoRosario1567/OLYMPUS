"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api, ApiError, type OlympusSkill, type SaaSOrganization, type SkillsCatalog } from "@/services/api";

const STATUS: Record<string, { label: string; style: string }> = {
  active: { label: "Ativa", style: "bg-emerald-400/[0.09] text-emerald-300" },
  review_required: { label: "Aguardando revisão", style: "bg-amber-300/[0.09] text-amber-200" },
  blocked: { label: "Bloqueada", style: "bg-rose-400/[0.09] text-rose-300" },
  disabled: { label: "Desativada", style: "bg-white/[0.05] text-zinc-500" },
};

export default function SkillsPage() {
  const ready = useRequireAuth();
  const [catalog, setCatalog] = useState<SkillsCatalog | null>(null);
  const [organization, setOrganization] = useState<SaaSOrganization | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const canManage = organization?.role === "owner" || organization?.role === "admin";

  async function load() {
    const [skills, current] = await Promise.all([api.listarSkills(), api.obterOrganizacao()]);
    setCatalog(skills); setOrganization(current);
  }
  useEffect(() => { if (ready) void load().catch(() => setError("Não foi possível carregar as skills.")); }, [ready]);

  const groups = useMemo(() => ({
    core: catalog?.skills.filter((skill) => skill.source === "builtin") ?? [],
    external: catalog?.skills.filter((skill) => skill.source !== "builtin") ?? [],
  }), [catalog]);

  async function importSkill(event: FormEvent) {
    event.preventDefault(); if (!url.trim() || busy) return;
    setBusy("import"); setError(""); setNotice("");
    try {
      const result = await api.importarSkillGitHub(url.trim());
      setNotice(result.findings.length ? "A importação foi bloqueada pelos controles de segurança." : "Importada para revisão. Nenhuma instrução foi executada.");
      setUrl(""); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Não foi possível importar esta skill."); }
    finally { setBusy(""); }
  }

  async function approve(skill: OlympusSkill) {
    setBusy(skill.id); setError(""); setNotice("");
    try { await api.aprovarSkill(skill.id); setNotice(`${skill.name} foi ativada.`); await load(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Não foi possível ativar esta skill."); }
    finally { setBusy(""); }
  }

  async function disable(skill: OlympusSkill) {
    setBusy(skill.id); setError(""); setNotice("");
    try { await api.desativarSkill(skill.id); setNotice(`${skill.name} foi desativada sem apagar seu conteúdo.`); await load(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Não foi possível desativar esta skill."); }
    finally { setBusy(""); }
  }

  if (!ready) return null;
  return <PainelShell><main className="mx-auto max-w-6xl px-5 py-10 md:px-10">
    <div><p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-500/70">Conhecimento operacional</p><h1 className="mt-2 text-2xl font-semibold text-zinc-100">Skills do Olympus</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-500">Instruções reutilizáveis reduzem raciocínio repetido, orientam cada IA e definem como a entrega será verificada.</p></div>
    {error && <p className="mt-6 rounded-xl border border-rose-400/15 bg-rose-400/[0.05] px-4 py-3 text-sm text-rose-200">{error}</p>}
    {notice && <p className="mt-6 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.05] px-4 py-3 text-sm text-emerald-200">{notice}</p>}

    <section className="mt-8 rounded-2xl border border-white/[0.08] bg-white/[0.022] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="font-medium text-zinc-100">Adicionar pelo GitHub</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-zinc-600">Aceita repositório público HTTPS com SKILL.md. O Olympus limita o arquivo, bloqueia caminhos perigosos, procura instruções críticas e exige aprovação administrativa.</p></div><span className="rounded-full bg-cyan-400/[0.08] px-3 py-1 text-[11px] text-cyan-300">Execução automática desativada</span></div>
      <form onSubmit={importSkill} className="mt-5 flex flex-col gap-2 sm:flex-row"><input aria-label="Repositório da skill" value={url} onChange={(event) => setUrl(event.target.value)} disabled={!canManage || busy === "import"} placeholder="https://github.com/organizacao/repositorio" className="min-w-0 flex-1 rounded-xl border border-white/[0.09] bg-[#171717] px-4 py-3 text-sm text-zinc-200 outline-none placeholder:text-zinc-700" /><button disabled={!canManage || !url.trim() || busy === "import"} className="rounded-xl bg-zinc-100 px-5 py-3 text-sm font-medium text-zinc-950 disabled:bg-zinc-700 disabled:text-zinc-500">{busy === "import" ? "Analisando…" : "Importar para revisão"}</button></form>
    </section>

    <section className="mt-6 grid gap-3 md:grid-cols-3">
      <CapabilityRule title="Skills" text="Entram como contratos revisáveis, com gatilhos, limites e critérios de conclusão." />
      <CapabilityRule title="MCP e conectores" text="Só aparecem como conectados após servidor detectado, permissões definidas e teste real." />
      <CapabilityRule title="Apps e bibliotecas" text="Permanecem opcionais e nunca são anunciados como capacidade nativa sem integração executável." />
    </section>

    <SkillSection title="Skills proprietárias" description="Contratos mantidos e ativados pelo próprio Olympus." skills={groups.core} busy={busy} canManage={Boolean(canManage)} onApprove={approve} onDisable={disable} />
    <SkillSection title="Skills externas" description="Conteúdo de terceiros permanece isolado até passar pela revisão." skills={groups.external} busy={busy} canManage={Boolean(canManage)} onApprove={approve} onDisable={disable} />
  </main></PainelShell>;
}

function CapabilityRule({ title, text }: { title: string; text: string }) {
  return <article className="rounded-2xl border border-white/[0.07] bg-white/[0.018] p-4"><h2 className="text-xs font-medium text-zinc-300">{title}</h2><p className="mt-2 text-[11px] leading-5 text-zinc-600">{text}</p></article>;
}

function SkillSection({ title, description, skills, busy, canManage, onApprove, onDisable }: { title: string; description: string; skills: OlympusSkill[]; busy: string; canManage: boolean; onApprove: (skill: OlympusSkill) => void; onDisable: (skill: OlympusSkill) => void }) {
  return <section className="mt-10"><div className="mb-4"><h2 className="font-medium text-zinc-100">{title}</h2><p className="mt-1 text-xs text-zinc-600">{description}</p></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{skills.map((skill) => {
    const status = STATUS[skill.status] ?? { label: skill.status, style: "bg-white/[0.05] text-zinc-500" };
    return <article key={skill.id} className="rounded-2xl border border-white/[0.07] bg-white/[0.022] p-5"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-medium text-zinc-100">{skill.name}</h3><p className="mt-1 text-[10px] text-zinc-600">v{skill.version} · {skill.source === "builtin" ? "Olympus" : "Externa"}</p></div><span className={`rounded-full px-2.5 py-1 text-[10px] ${status.style}`}>{status.label}</span></div><p className="mt-4 min-h-10 text-xs leading-5 text-zinc-600">{skill.description}</p><div className="mt-4 border-t border-white/[0.055] pt-3 text-[11px] text-zinc-600"><p>{skill.allowed_actions.length} ações permitidas · {skill.completion_checks.length} verificações</p>{skill.license && <p className="mt-1">Licença: {skill.license}</p>}</div>{skill.source !== "builtin" && <details className="mt-3 rounded-lg border border-white/[0.06] px-3 py-2 text-[11px] text-zinc-500"><summary className="cursor-pointer text-zinc-400">Inspecionar instruções importadas</summary><ul className="mt-2 list-disc space-y-1 pl-4">{skill.guidance.map((item, index) => <li key={index}>{item}</li>)}</ul>{skill.source_url && <p className="mt-2 break-all text-cyan-400/70">{skill.source_url}</p>}</details>}{skill.status === "review_required" && <button onClick={() => onApprove(skill)} disabled={!canManage || busy === skill.id} className="mt-4 w-full rounded-lg border border-white/[0.09] px-3 py-2 text-xs text-zinc-300 disabled:opacity-40">{busy === skill.id ? "Ativando…" : "Confirmar revisão e ativar"}</button>}{skill.source !== "builtin" && skill.status === "active" && <button onClick={() => onDisable(skill)} disabled={!canManage || busy === skill.id} className="mt-4 w-full rounded-lg border border-white/[0.07] px-3 py-2 text-xs text-zinc-500 disabled:opacity-40">Desativar sem apagar</button>}</article>;
  })}{!skills.length && <div className="rounded-2xl border border-dashed border-white/[0.08] p-8 text-center text-sm text-zinc-600">Nenhuma skill nesta categoria.</div>}</div></section>;
}
