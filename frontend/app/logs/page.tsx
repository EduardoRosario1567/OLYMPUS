"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { Log } from "@/types/dashboard";

const NIVEL_OPCOES = ["debug", "info", "warning", "error", "critical"];

const LEVEL_COLOR: Record<string, string> = {
  info: "text-zinc-400",
  warning: "text-amber-400",
  error: "text-red-400",
  critical: "text-red-400",
  debug: "text-zinc-600",
};

function formatarHorario(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit", day: "2-digit", month: "2-digit" });
}

function LogsConteudo() {
  const pronto = useRequireAuth();
  const searchParams = useSearchParams();
  const projectIdFiltro = searchParams.get("project_id") ?? undefined;
  const executionIdFiltro = searchParams.get("execution_id") ?? undefined;

  const [nivelFiltro, setNivelFiltro] = useState("");
  const [busca, setBusca] = useState("");
  const [logs, setLogs] = useState<Log[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto) return;

    const chamada = busca.trim()
      ? api.buscarLogs(busca.trim())
      : api.listarLogs({ project_id: projectIdFiltro, execution_id: executionIdFiltro, level: nivelFiltro || undefined });

    chamada.then(setLogs).catch(() => setErro("Não foi possível carregar os logs."));
  }, [pronto, projectIdFiltro, executionIdFiltro, nivelFiltro, busca]);

  if (!pronto) return null;

  return (
    <PainelShell>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-50">Logs</h1>
          <p className="text-sm text-zinc-500">
            {projectIdFiltro ? "Logs do projeto selecionado" : "Todos os logs"}
          </p>
        </header>

        <div className="mb-4 flex flex-wrap gap-2">
          <Input
            placeholder="Buscar em mensagem/evento..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="max-w-xs"
          />
          <select
            value={nivelFiltro}
            onChange={(e) => setNivelFiltro(e.target.value)}
            disabled={Boolean(busca.trim())}
            className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2 text-sm text-zinc-300 disabled:opacity-50"
          >
            <option value="">Todos os níveis</option>
            {NIVEL_OPCOES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>

        {erro && <p className="mb-6 text-sm text-red-400">{erro}</p>}
        {!logs && !erro && <p className="text-sm text-zinc-500">Carregando...</p>}

        {logs && (
          <Card className="overflow-hidden p-0">
            {logs.length === 0 ? (
              <p className="px-6 py-8 text-center text-sm text-zinc-600">Nenhum log encontrado.</p>
            ) : (
              <ul className="divide-y divide-white/5">
                {logs.map((log) => (
                  <li key={log.id} className="px-6 py-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className={`text-xs font-medium uppercase ${LEVEL_COLOR[log.level] ?? "text-zinc-400"}`}>
                        {log.level} · {log.event_type}
                      </span>
                      <span className="text-xs text-zinc-500">{formatarHorario(log.created_at)}</span>
                    </div>
                    <p className="mt-1 text-zinc-300">{log.message}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </main>
    </PainelShell>
  );
}

export default function LogsPage() {
  return (
    <Suspense fallback={null}>
      <LogsConteudo />
    </Suspense>
  );
}
