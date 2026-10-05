"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PainelShell } from "@/components/layout/painel-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRequireAuth } from "@/hooks/useAuth";
import { api, type CloudProject } from "@/services/api";

function formatarData(value: number) {
  return new Date(value * 1000).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export default function ProjetosPage() {
  const pronto = useRequireAuth();
  const [projetos, setProjetos] = useState<CloudProject[] | null>(null);
  const [nome, setNome] = useState("");
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto) return;
    api.listarCloudProjetos().then(setProjetos).catch(() => setErro("Não foi possível carregar seus projetos."));
  }, [pronto]);

  async function criar() {
    if (!nome.trim() || criando) return;
    setCriando(true); setErro(null);
    try {
      const projeto = await api.criarCloudProjeto({ name: nome.trim() });
      setProjetos((current) => [projeto, ...(current ?? [])]);
      setNome("");
    } catch { setErro("Não foi possível criar o projeto."); }
    finally { setCriando(false); }
  }

  async function baixar(projeto: CloudProject) {
    try { await api.baixarCloudProjeto(projeto.project_id); setErro(null); }
    catch { setErro(`Não foi possível baixar ${projeto.name}.`); }
  }

  if (!pronto) return null;

  return <PainelShell>
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-8"><p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-700">Seu espaço</p><h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-zinc-100">Projetos</h1><p className="mt-2 text-sm text-zinc-500">Continue uma criação, consulte versões ou baixe seus arquivos.</p></header>
      <div className="mb-6 flex gap-2 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-2"><Input aria-label="Nome do novo projeto" value={nome} onChange={(event) => setNome(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void criar(); } }} placeholder="Nome do novo projeto" /><Button type="button" onClick={criar} disabled={!nome.trim() || criando}>{criando ? "Criando" : "Criar projeto"}</Button></div>
      {erro && <p className="mb-4 rounded-xl bg-rose-400/[0.07] px-4 py-3 text-sm text-rose-200/80">{erro}</p>}
      {!projetos && !erro && <p className="py-16 text-center text-sm text-zinc-600">Carregando projetos...</p>}
      {projetos?.length === 0 && <div className="rounded-2xl border border-dashed border-white/[0.08] py-16 text-center"><p className="text-sm text-zinc-500">Seu primeiro projeto começa com uma ideia.</p><Link href="/missao" className="mt-4 inline-flex rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-black">Nova missão</Link></div>}
      <div className="grid gap-3 sm:grid-cols-2">{projetos?.map((projeto) => <article key={projeto.project_id} className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5 transition hover:border-white/[0.12] hover:bg-white/[0.03]"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><h2 className="truncate font-medium text-zinc-200">{projeto.name}</h2><p className="mt-1 text-xs text-zinc-600">Atualizado em {formatarData(projeto.updated_at)}</p></div><span className="shrink-0 text-xs text-zinc-500">Projeto salvo</span></div><div className="mt-6 flex items-center gap-2"><Link href={`/missao?project_id=${encodeURIComponent(projeto.project_id)}`} className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-black hover:bg-zinc-200">Abrir projeto</Link><button type="button" onClick={() => void baixar(projeto)} className="rounded-lg px-3 py-2 text-xs text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-200">Baixar</button></div></article>)}</div>
    </main>
  </PainelShell>;
}
