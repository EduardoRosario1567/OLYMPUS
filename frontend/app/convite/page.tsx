"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Brand } from "@/components/layout/sidebar";
import { api, ApiError } from "@/services/api";

function InviteForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const token = params.get("token") || "";

  async function accept() {
    setBusy(true); setError("");
    try {
      const result = await api.aceitarConvite(token, email, password);
      localStorage.setItem("olympus_token", result.access_token);
      router.replace("/missao");
    } catch (e) { setError(e instanceof ApiError ? e.message : "Não foi possível aceitar o convite."); }
    finally { setBusy(false); }
  }

  return <div className="w-full max-w-sm"><div className="mb-10 flex justify-center"><Brand /></div><div className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-6"><h1 className="text-xl font-semibold">Entrar na equipe</h1><p className="mt-2 text-sm text-zinc-500">Use o email que recebeu o convite e crie sua senha.</p>{error && <p className="mt-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}<div className="mt-6 space-y-3"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Seu email" className="w-full rounded-xl border border-white/10 bg-[#151515] px-3 py-3 text-sm outline-hidden focus:border-white/20"/><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Crie uma senha segura" className="w-full rounded-xl border border-white/10 bg-[#151515] px-3 py-3 text-sm outline-hidden focus:border-white/20"/><button onClick={() => void accept()} disabled={busy || !token || !email || password.length < 10} className="w-full rounded-xl bg-zinc-100 px-4 py-3 text-sm font-medium text-zinc-950 disabled:opacity-40">Aceitar convite</button></div></div></div>;
}

export default function InvitePage() {
  return <main className="grid min-h-screen place-items-center bg-[#101010] px-5"><Suspense><InviteForm /></Suspense></main>;
}
