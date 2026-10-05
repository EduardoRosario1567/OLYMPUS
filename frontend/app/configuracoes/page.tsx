"use client";

import { useEffect, useMemo, useState } from "react";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api, ApiError, SaaSAuditEvent, SaaSMember, SaaSOrganization, SaaSUsage } from "@/services/api";

const ROLE_LABEL: Record<string, string> = { owner: "Proprietário", admin: "Administrador", builder: "Construtor", viewer: "Leitor" };

export default function ConfiguracoesPage() {
  const ready = useRequireAuth();
  const [organization, setOrganization] = useState<SaaSOrganization | null>(null);
  const [organizations, setOrganizations] = useState<SaaSOrganization[]>([]);
  const [members, setMembers] = useState<SaaSMember[]>([]);
  const [usage, setUsage] = useState<SaaSUsage | null>(null);
  const [audit, setAudit] = useState<SaaSAuditEvent[]>([]);
  const [chainValid, setChainValid] = useState(true);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "builder" | "viewer">("builder");
  const [inviteUrl, setInviteUrl] = useState("");
  const [newOrganization, setNewOrganization] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const canManage = organization?.role === "owner" || organization?.role === "admin";
  const canAudit = organization?.role === "owner" || organization?.role === "admin";
  const planName = useMemo(() => ({ founder: "Fundador", starter: "Inicial", professional: "Profissional", business: "Business" }[usage?.plan_id || ""] || usage?.plan_id), [usage]);

  async function load() {
    setError("");
    try {
      const [current, all, people, counters] = await Promise.all([
        api.obterOrganizacao(), api.listarOrganizacoes(), api.listarMembros(), api.obterUso(),
      ]);
      setOrganization(current); setOrganizations(all); setMembers(people); setUsage(counters);
      if (current.role === "owner" || current.role === "admin") {
        const history = await api.listarAuditoria();
        setAudit(history.events); setChainValid(history.chain_valid);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não foi possível carregar a organização.");
    }
  }

  useEffect(() => { if (ready) void load(); }, [ready]);

  async function invite() {
    setBusy(true); setError(""); setInviteUrl("");
    try {
      const result = await api.convidarMembro(email, role);
      setInviteUrl(`${window.location.origin}/convite?token=${encodeURIComponent(result.invitation_token)}`);
      setEmail(""); await load();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Não foi possível criar o convite."); }
    finally { setBusy(false); }
  }

  async function switchOrganization(id: string) {
    if (id === organization?.organization_id) return;
    await api.trocarOrganizacao(id);
    window.location.reload();
  }

  async function createOrganization() {
    if (!newOrganization.trim()) return;
    setBusy(true); setError("");
    try {
      const created = await api.criarOrganizacao(newOrganization.trim());
      await api.trocarOrganizacao(created.organization_id);
      window.location.reload();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Não foi possível criar a organização."); }
    finally { setBusy(false); }
  }

  if (!ready) return null;
  return <PainelShell><main className="mx-auto max-w-5xl px-5 py-10 md:px-10">
    <div className="mb-8"><p className="text-xs font-medium uppercase tracking-[0.2em] text-zinc-600">Seu espaço</p><h1 className="mt-2 text-2xl font-semibold text-zinc-100">Organização</h1><p className="mt-2 text-sm text-zinc-500">Equipe, acesso e uso em um só lugar.</p></div>
    {error && <div className="mb-5 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-300">{error}</div>}

    <section className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5">
      <div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-medium text-zinc-100">{organization?.name || "Carregando…"}</h2><p className="mt-1 text-xs text-zinc-600">{ROLE_LABEL[organization?.role || ""]}</p></div>
      {organizations.length > 1 && <select aria-label="Trocar organização" value={organization?.organization_id || ""} onChange={(e) => void switchOrganization(e.target.value)} className="rounded-lg border border-white/10 bg-[#171717] px-3 py-2 text-sm text-zinc-300">{organizations.map((item) => <option key={item.organization_id} value={item.organization_id}>{item.name}</option>)}</select>}</div>
    </section>

    <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_0.6fr]">
      <section className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><div className="flex items-center justify-between"><h2 className="font-medium text-zinc-100">Equipe</h2><span className="text-xs text-zinc-600">{members.length} membro{members.length === 1 ? "" : "s"}</span></div>
        <div className="mt-4 divide-y divide-white/[0.06]">{members.map((member) => <div key={member.user_id} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate text-sm text-zinc-200">{member.email}</p><p className="mt-0.5 text-xs text-zinc-600">{ROLE_LABEL[member.role]}</p></div>{member.role !== "owner" && canManage && <div className="flex items-center gap-1"><select value={member.role} aria-label={`Papel de ${member.email}`} onChange={async (e) => { await api.alterarPapelMembro(member.user_id, e.target.value as "admin" | "builder" | "viewer"); await load(); }} className="rounded-lg border border-white/10 bg-[#171717] px-2 py-1.5 text-xs text-zinc-400"><option value="admin">Administrador</option><option value="builder">Construtor</option><option value="viewer">Leitor</option></select><button aria-label={`Remover ${member.email}`} onClick={async () => { if (!window.confirm(`Remover ${member.email} da organização?`)) return; await api.removerMembro(member.user_id); await load(); }} className="rounded-lg px-2 py-1.5 text-xs text-zinc-600 hover:bg-red-500/10 hover:text-red-300">Remover</button></div>}</div>)}</div>
        {canManage && <div className="mt-5 border-t border-white/[0.06] pt-5"><p className="mb-3 text-sm font-medium text-zinc-300">Convidar alguém</p><div className="flex flex-col gap-2 sm:flex-row"><input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="email@empresa.com" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#151515] px-3 py-2.5 text-sm outline-none focus:border-white/20"/><select value={role} onChange={(e) => setRole(e.target.value as typeof role)} className="rounded-xl border border-white/10 bg-[#151515] px-3 py-2.5 text-sm text-zinc-400"><option value="builder">Construtor</option><option value="admin">Administrador</option><option value="viewer">Leitor</option></select><button disabled={busy || !email} onClick={() => void invite()} className="rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-medium text-zinc-950 disabled:opacity-40">Criar convite</button></div>{inviteUrl && <div className="mt-3 rounded-xl bg-black/20 p-3"><p className="text-xs text-zinc-500">Link de uso único — compartilhe por um canal seguro.</p><div className="mt-2 flex gap-2"><input readOnly value={inviteUrl} className="min-w-0 flex-1 bg-transparent text-xs text-zinc-300 outline-none"/><button onClick={() => void navigator.clipboard.writeText(inviteUrl)} className="text-xs text-zinc-400 hover:text-white">Copiar</button></div></div>}</div>}
      </section>

      <section className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><h2 className="font-medium text-zinc-100">Plano {planName}</h2><p className="mt-1 text-xs text-emerald-400">{usage?.subscription_status === "active" ? "Ativo" : usage?.subscription_status}</p><div className="mt-5 space-y-4"><Usage label="Missões neste mês" value={usage?.usage.missions_month || 0} limit={usage?.limits.missions_month}/><Usage label="Publicações neste mês" value={usage?.usage.deployments_month || 0} limit={usage?.limits.deployments_month}/><Usage label="Membros" value={members.length} limit={usage?.limits.members}/></div></section>
    </div>

    {canAudit && <details className="mt-5 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><summary className="cursor-pointer list-none text-sm font-medium text-zinc-300">Atividade e segurança <span className={chainValid ? "text-emerald-500" : "text-red-400"}>· {chainValid ? "íntegra" : "verificação necessária"}</span></summary><div className="mt-4 divide-y divide-white/[0.05]">{audit.slice(0, 30).map((event) => <div key={event.sequence} className="flex items-center justify-between gap-4 py-2.5 text-xs"><span className="text-zinc-400">{event.action.replaceAll(".", " · ")}</span><time className="shrink-0 text-zinc-700">{new Date(event.created_at * 1000).toLocaleString("pt-BR")}</time></div>)}</div></details>}
    <details className="mt-5 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><summary className="cursor-pointer list-none text-sm text-zinc-500">Criar outra organização</summary><div className="mt-4 flex gap-2"><input value={newOrganization} onChange={(e) => setNewOrganization(e.target.value)} placeholder="Nome da organização" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-[#151515] px-3 py-2.5 text-sm outline-none"/><button disabled={busy || !newOrganization.trim()} onClick={() => void createOrganization()} className="rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-medium text-zinc-950 disabled:opacity-40">Criar</button></div></details>
  </main></PainelShell>;
}

function Usage({ label, value, limit = 0 }: { label: string; value: number; limit?: number }) {
  const percentage = limit ? Math.min(100, (value / limit) * 100) : 0;
  return <div><div className="flex justify-between text-xs"><span className="text-zinc-500">{label}</span><span className="text-zinc-400">{value} / {limit || "—"}</span></div><div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-zinc-400" style={{ width: `${percentage}%` }}/></div></div>;
}
