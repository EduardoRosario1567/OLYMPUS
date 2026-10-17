"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { CloudExecution } from "@/services/api";

const STATUS_OPCOES = ["queued", "running", "verifying", "completed", "failed", "blocked", "cancelled", "waiting_decision", "paused_capacity"];
const STATUS_LABEL: Record<string, string> = { queued: "Na fila", running: "Construindo", verifying: "Verificando", completed: "Concluída", failed: "Interrompida", blocked: "Aguardando", cancelled: "Cancelada", paused_capacity: "Pausada por capacidade", waiting_decision: "Aguardando decisão" };

function formatarHorario(value: number) {
  return new Date(value * 1000).toLocaleString("pt-BR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

function ExecucoesConteudo() {
  const pronto = useRequireAuth();
  const searchParams = useSearchParams();
  const projectIdFiltro = searchParams.get("project_id") ?? undefined;

  const [statusFiltro, setStatusFiltro] = useState<string>("");
  const [execucoes, setExecucoes] = useState<CloudExecution[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto) return;
    api
      .listarCloudExecucoes({ project_id: projectIdFiltro, status: statusFiltro || undefined })
      .then(setExecucoes)
      .catch(() => setErro("Não foi possível carregar as execuções."));
  }, [pronto, projectIdFiltro, statusFiltro]);

  if (!pronto) return null;

  return (
    <PainelShell>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-50">Histórico</h1>
          <p className="text-sm text-zinc-500">
            {projectIdFiltro ? "Missões do projeto selecionado" : "Missões da organização atual"}
          </p>
        </header>

        <div className="mb-4 flex gap-2">
          <select
            aria-label="Filtrar histórico por status"
            value={statusFiltro}
            onChange={(e) => setStatusFiltro(e.target.value)}
            className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2 text-sm text-zinc-300"
          >
            <option value="">Todos os status</option>
            {STATUS_OPCOES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </div>

        {erro && <p className="mb-6 text-sm text-red-400">{erro}</p>}
        {!execucoes && !erro && <p className="text-sm text-zinc-500">Carregando...</p>}

        {execucoes && (
          <div className="space-y-2">
            {execucoes.length === 0 ? (
              <p className="px-6 py-8 text-center text-sm text-zinc-600">Nenhuma execução encontrada.</p>
            ) : (
              execucoes.map((e) => (
                <Link key={e.execution_id} href={`/missao?project_id=${encodeURIComponent(e.project_id)}`} className="block rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4 transition hover:bg-white/[0.035]">
                  <div className="flex items-start justify-between gap-4"><p className="line-clamp-2 text-sm text-zinc-300">{e.task}</p><span className="shrink-0 text-xs text-zinc-500">{STATUS_LABEL[e.status] || e.status}</span></div>
                  <div className="mt-3 flex gap-3 text-xs text-zinc-700"><time>{formatarHorario(e.created_at)}</time><span>·</span><span>{e.project_id}</span></div>
                </Link>
              ))
            )}
          </div>
        )}
      </main>
    </PainelShell>
  );
}

export default function ExecucoesPage() {
  return (
    <Suspense fallback={null}>
      <ExecucoesConteudo />
    </Suspense>
  );
}
