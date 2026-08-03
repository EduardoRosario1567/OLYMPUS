"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardLabel, CardValue } from "@/components/ui/card";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { DashboardSummary, Execucao, Log } from "@/types/dashboard";

function formatarMoeda(valor: number) {
  return `US$ ${valor.toFixed(2)}`;
}

function formatarPercentual(valor: number) {
  return `${(valor * 100).toFixed(1)}%`;
}

function formatarHorario(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

const LEVEL_COLOR: Record<string, string> = {
  info: "text-zinc-400",
  warning: "text-amber-400",
  error: "text-red-400",
  critical: "text-red-400",
  debug: "text-zinc-600",
};

export default function DashboardPage() {
  const pronto = useRequireAuth();
  const [resumo, setResumo] = useState<DashboardSummary | null>(null);
  const [execucoes, setExecucoes] = useState<Execucao[] | null>(null);
  const [logs, setLogs] = useState<Log[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto) return;
    Promise.all([
      api.dashboardSummary(),
      api.listarExecucoes({ limit: 5 }),
      api.listarLogs({ limit: 5 }),
    ])
      .then(([s, e, l]) => {
        setResumo(s);
        setExecucoes(e);
        setLogs(l);
      })
      .catch(() => setErro("Não foi possível carregar o dashboard."));
  }, [pronto]);

  if (!pronto) return null;

  const carregando = !resumo && !erro;

  return (
    <PainelShell>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-50">Dashboard</h1>
          <p className="text-sm text-zinc-500">Visão geral do sistema de orquestração</p>
        </header>

        {erro && <p className="mb-6 text-sm text-red-400">{erro}</p>}
        {carregando && <p className="text-sm text-zinc-500">Carregando...</p>}

        {resumo && (
          <>
            <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Card>
                <CardLabel>Projetos</CardLabel>
                <CardValue>{resumo.total_projetos}</CardValue>
              </Card>
              <Card>
                <CardLabel>Execuções</CardLabel>
                <CardValue>{resumo.total_execucoes}</CardValue>
              </Card>
              <Card>
                <CardLabel>Custo Total</CardLabel>
                <CardValue>{formatarMoeda(resumo.custo_total)}</CardValue>
              </Card>
              <Card>
                <CardLabel>Latência Média</CardLabel>
                <CardValue>{Math.round(resumo.latencia_media_ms)} ms</CardValue>
              </Card>
              <Card>
                <CardLabel>Taxa de Sucesso</CardLabel>
                <CardValue>{formatarPercentual(resumo.taxa_sucesso)}</CardValue>
              </Card>
              <Card>
                <CardLabel>Taxa de Fallback</CardLabel>
                <CardValue>{formatarPercentual(resumo.fallback_rate)}</CardValue>
              </Card>
              <Card>
                <CardLabel>Modelo Mais Usado</CardLabel>
                <CardValue className={!resumo.modelo_mais_usado ? "text-zinc-600" : undefined}>
                  {resumo.modelo_mais_usado ?? "não disponível"}
                </CardValue>
              </Card>
            </section>

            {/* agente ainda não é entidade real — nunca dado fake */}
            {!resumo.agentes_implementado && (
              <section className="mt-4">
                <Card className="opacity-50">
                  <CardLabel>Agentes</CardLabel>
                  <p className="mt-2 text-sm text-zinc-500">Pendente de modelagem</p>
                </Card>
              </section>
            )}

            <div className="mt-8 grid gap-8 lg:grid-cols-2">
              <section>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-medium text-zinc-400">Execuções Recentes</h2>
                  <Link href="/execucoes" className="text-xs text-zinc-500 hover:text-zinc-300">
                    Ver todas →
                  </Link>
                </div>
                <Card className="overflow-hidden p-0">
                  <ul className="divide-y divide-white/5">
                    {execucoes?.length === 0 && (
                      <li className="px-6 py-6 text-center text-sm text-zinc-600">Nenhuma execução ainda.</li>
                    )}
                    {execucoes?.map((exec) => (
                      <li key={exec.id}>
                        <Link
                          href={`/execucoes?project_id=${exec.project_id}`}
                          className="flex items-center justify-between px-6 py-3 text-sm hover:bg-white/[0.02]"
                        >
                          <div>
                            <p className="capitalize text-zinc-200">{exec.status}</p>
                            <p className="text-xs text-zinc-500">{formatarHorario(exec.created_at)}</p>
                          </div>
                          <div className="text-right text-zinc-400">
                            <p>{formatarMoeda(exec.total_cost)}</p>
                            <p className="text-xs">{exec.modelo_principal ?? "não disponível"}</p>
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </Card>
              </section>

              <section>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-medium text-zinc-400">Logs Recentes</h2>
                  <Link href="/logs" className="text-xs text-zinc-500 hover:text-zinc-300">
                    Ver todos →
                  </Link>
                </div>
                <Card className="overflow-hidden p-0">
                  <ul className="divide-y divide-white/5">
                    {logs?.length === 0 && (
                      <li className="px-6 py-6 text-center text-sm text-zinc-600">Nenhum log ainda.</li>
                    )}
                    {logs?.map((log) => (
                      <li key={log.id} className="px-6 py-3 text-sm">
                        <div className="flex items-center justify-between">
                          <span className={`text-xs font-medium uppercase ${LEVEL_COLOR[log.level] ?? "text-zinc-400"}`}>
                            {log.level}
                          </span>
                          <span className="text-xs text-zinc-500">{formatarHorario(log.created_at)}</span>
                        </div>
                        <p className="mt-1 text-zinc-300">{log.message}</p>
                      </li>
                    ))}
                  </ul>
                </Card>
              </section>
            </div>
          </>
        )}
      </main>
    </PainelShell>
  );
}
