"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export default function RootPage() {
  const router = useRouter();
  const { carregando, autenticado } = useAuth();

  useEffect(() => {
    if (carregando) return;
    router.replace(autenticado ? "/dashboard" : "/login");
  }, [carregando, autenticado, router]);

  return null;
}
