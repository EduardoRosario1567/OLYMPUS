"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/card";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { Execucao } from "@/types/dashboard";

const STATUS_OPCOES = ["pending", "running", "completed", "failed", "partial"];

function formatarHorario(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

function formatarMoeda(v: number) {
  return `US$ ${v.toFixed(2)}`;
}

function ExecucoesConteudo() {
  const pronto = useRequireAuth();
  const searchParams = useSearchParams();
  const projectIdFiltro = searchParams.get("project_id") ?? undefined;

  const [statusFiltro, setStatusFiltro] = useState<string>("");
  const [execucoes, setExecucoes] = useState<Execucao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto) return;
    api
      .listarExecucoes({ project_id: projectIdFiltro, status: statusFiltro || undefined })
      .then(setExecucoes)
      .catch(() => setErro("Não foi possível carregar as execuções."));
  }, [pronto, projectIdFiltro, statusFiltro]);

  if (!pronto) return null;

  return (
    <PainelShell>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-50">Execuções</h1>
          <p className="text-sm text-zinc-500">
            {projectIdFiltro ? "Execuções do projeto selecionado" : "Todas as execuções"}
          </p>
        </header>

        <div className="mb-4 flex gap-2">
          <select
            value={statusFiltro}
            onChange={(e) => setStatusFiltro(e.target.value)}
            className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2 text-sm text-zinc-300"
          >
            <option value="">Todos os status</option>
            {STATUS_OPCOES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {erro && <p className="mb-6 text-sm text-red-400">{erro}</p>}
        {!execucoes && !erro && <p className="text-sm text-zinc-500">Carregando...</p>}

        {execucoes && (
          <Card className="overflow-hidden p-0">
            {execucoes.length === 0 ? (
              <p className="px-6 py-8 text-center text-sm text-zinc-600">Nenhuma execução encontrada.</p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-zinc-500">
                    <th className="px-6 py-3 font-medium">Data</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Modelo Principal</th>
                    <th className="px-6 py-3 font-medium">Fallback</th>
                    <th className="px-6 py-3 font-medium">Custo</th>
                    <th className="px-6 py-3 font-medium">Latência</th>
                    <th className="px-6 py-3 font-medium">Confiança</th>
                  </tr>
                </thead>
                <tbody>
                  {execucoes.map((e) => (
                    <tr key={e.id} className="border-b border-white/5 last:border-0">
                      <td className="px-6 py-3 text-zinc-400">{formatarHorario(e.created_at)}</td>
                      <td className="px-6 py-3 capitalize text-zinc-200">{e.status}</td>
                      <td className="px-6 py-3 text-zinc-400">{e.modelo_principal ?? "não disponível"}</td>
                      <td className="px-6 py-3 text-zinc-400">{e.fallback_usado ? "Sim" : "Não"}</td>
                      <td className="px-6 py-3 text-zinc-400">{formatarMoeda(e.total_cost)}</td>
                      <td className="px-6 py-3 text-zinc-400">{e.total_latency_ms} ms</td>
                      <td className="px-6 py-3 text-zinc-400">
                        {e.confianca_media != null ? `${(e.confianca_media * 100).toFixed(0)}%` : "não disponível"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
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
