"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";

const ITENS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/projetos", label: "Projetos" },
  { href: "/execucoes", label: "Execuções" },
  { href: "/logs", label: "Logs" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-white/10 px-4 py-8 md:flex">
      <div className="mb-8 px-2">
        <p className="text-sm font-semibold tracking-tight text-zinc-50">Olympus</p>
      </div>
      <nav className="flex flex-1 flex-col gap-1">
        {ITENS.map((item) => {
          const ativo = pathname === item.href || pathname?.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-lg px-3 py-2 text-sm transition-colors duration-150",
                ativo ? "bg-white/[0.06] text-zinc-50" : "text-zinc-500 hover:bg-white/[0.03] hover:text-zinc-300"
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <button
        onClick={logout}
        className="rounded-lg px-3 py-2 text-left text-sm text-zinc-500 transition-colors duration-150 hover:bg-white/[0.03] hover:text-zinc-300"
      >
        Sair
      </button>
    </aside>
  );
}
