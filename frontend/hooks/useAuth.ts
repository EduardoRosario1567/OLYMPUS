"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/services/api";

/** Evento global disparado pelo services/api.ts quando qualquer chamada leva 401.
 *  É o único lugar que decide "sessão expirou, volta pro login" — nenhuma
 *  página precisa mais tratar 401 no próprio catch. */
export const EVENTO_NAO_AUTORIZADO = "olympus:unauthorized";

export function useAuth() {
  const router = useRouter();
  const [carregando, setCarregando] = useState(true);
  const [autenticado, setAutenticado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setAutenticado(Boolean(localStorage.getItem("olympus_token")));
    setCarregando(false);
  }, []);

  const login = useCallback(
    async (email: string, senha: string, lembrar: boolean) => {
      setErro(null);
      try {
        const { access_token } = await api.login({ email, senha, lembrar });
        localStorage.setItem("olympus_token", access_token);
        setAutenticado(true);
        router.push("/missao");
      } catch (e) {
        setErro(e instanceof ApiError ? e.message : "Erro inesperado ao entrar.");
      }
    },
    [router]
  );

  const logout = useCallback(() => {
    localStorage.removeItem("olympus_token");
    setAutenticado(false);
    router.push("/login");
  }, [router]);

  return { carregando, autenticado, erro, login, logout };
}

/**
 * Guarda de autenticação para telas protegidas (Dashboard, Projetos,
 * Execuções, Logs). Antes, cada página checava localStorage e tratava 401
 * no próprio catch — 5 cópias da mesma lógica. Agora é só isto:
 *
 *   const pronto = useRequireAuth();
 *   if (!pronto) return null;
 */
export function useRequireAuth(): boolean {
  const router = useRouter();
  const [pronto, setPronto] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("olympus_token")) {
      router.replace("/login");
      return;
    }
    setPronto(true);
  }, [router]);

  useEffect(() => {
    function aoExpirar() {
      router.replace("/login");
    }
    window.addEventListener(EVENTO_NAO_AUTORIZADO, aoExpirar);
    return () => window.removeEventListener(EVENTO_NAO_AUTORIZADO, aoExpirar);
  }, [router]);

  return pronto;
}
