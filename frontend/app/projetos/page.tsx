"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PainelShell } from "@/components/layout/painel-shell";
import { useRequireAuth } from "@/hooks/useAuth";
import { api } from "@/services/api";
import type { Projeto } from "@/types/dashboard";

function formatarData(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR");
}

export default function ProjetosPage() {
  const pronto = useRequireAuth();
  const [projetos, setProjetos] = useState<Projeto[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!pronto) return;
    api
      .listarProjetos()
      .then(setProjetos)
      .catch(() => setErro("Não foi possível carregar os projetos."));
  }, [pronto]);

  if (!pronto) return null;

  return (
    <PainelShell>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-zinc-50">Projetos</h1>
            <p className="text-sm text-zinc-500">Projetos ativos no sistema de orquestração</p>
          </div>
          {/* fluxo de criação completo ainda não existe no backend */}
          <Button variant="ghost" disabled title="Em breve">
            Criar projeto (em breve)
          </Button>
        </header>

        {erro && <p className="mb-6 text-sm text-red-400">{erro}</p>}
        {!projetos && !erro && <p className="text-sm text-zinc-500">Carregando...</p>}

        {projetos && (
          <Card className="overflow-hidden p-0">
            {projetos.length === 0 ? (
              <p className="px-6 py-8 text-center text-sm text-zinc-600">
                Nenhum projeto criado ainda.
              </p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-zinc-500">
                    <th className="px-6 py-3 font-medium">Nome</th>
                    <th className="px-6 py-3 font-medium">Tipo</th>
                    <th className="px-6 py-3 font-medium">Complexidade</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Criado em</th>
                    <th className="px-6 py-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {projetos.map((p) => (
                    <tr key={p.id} className="border-b border-white/5 last:border-0">
                      <td className="px-6 py-3">
                        <p className="text-zinc-200">{p.name}</p>
                        {p.description && (
                          <p className="mt-0.5 max-w-xs truncate text-xs text-zinc-500">{p.description}</p>
                        )}
                      </td>
                      <td className="px-6 py-3 text-zinc-400">{p.product_type ?? "não disponível"}</td>
                      <td className="px-6 py-3 text-zinc-400">{p.complexity ?? "não disponível"}</td>
                      <td className="px-6 py-3 capitalize text-zinc-400">{p.status}</td>
                      <td className="px-6 py-3 text-zinc-400">{formatarData(p.created_at)}</td>
                      <td className="px-6 py-3">
                        <div className="flex gap-3 text-xs">
                          <Link href={`/execucoes?project_id=${p.id}`} className="text-zinc-400 hover:text-zinc-100">
                            Execuções
                          </Link>
                          <Link href={`/logs?project_id=${p.id}`} className="text-zinc-400 hover:text-zinc-100">
                            Logs
                          </Link>
                        </div>
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
