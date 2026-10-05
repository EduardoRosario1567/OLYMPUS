"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useRequireAuth } from "@/hooks/useAuth";

export default function DashboardPage() {
  const pronto = useRequireAuth();
  const router = useRouter();
  useEffect(() => { if (pronto) router.replace("/missao"); }, [pronto, router]);
  return null;
}
