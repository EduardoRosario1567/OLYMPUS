"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const { login, erro, carregando, autenticado } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [lembrar, setLembrar] = useState(false);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!carregando && autenticado) {
      router.replace("/missao");
    }
  }, [carregando, autenticado, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    await login(email, senha, lembrar);
    setEnviando(false);
  }

  if (carregando || autenticado) return null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#101010] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span role="img" aria-label="Símbolo de Zeus do Olympus" className="mx-auto block h-28 w-28 bg-contain bg-center bg-no-repeat" style={{ backgroundImage: "url('/olympus-mark.png?v=2.6.2')" }} />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-zinc-50">Entrar no Olympus</h1>
          <p className="mt-2 text-sm text-zinc-500">Continue de onde parou.</p>
        </div>

        <Card>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-zinc-400">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="senha" className="mb-1.5 block text-xs font-medium text-zinc-400">
                Senha
              </label>
              <Input
                id="senha"
                type="password"
                autoComplete="current-password"
                required
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-zinc-400">
              <input
                type="checkbox"
                checked={lembrar}
                onChange={(e) => setLembrar(e.target.checked)}
                className="h-4 w-4 rounded border-white/20 bg-transparent"
              />
              Lembrar acesso
            </label>

            {erro && <p className="text-sm text-red-400">{erro}</p>}

            <Button type="submit" disabled={enviando} className="mt-2">
              {enviando ? "Entrando..." : "Entrar"}
            </Button>

          </form>
        </Card>
      </div>
    </main>
  );
}
