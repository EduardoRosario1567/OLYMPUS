import type { ReactNode } from "react";
import { MobileNav, Sidebar } from "./sidebar";

export function PainelShell({ children }: { children: ReactNode }) {
  return <div className="app-shell min-h-screen md:flex"><div className="hidden md:block"><Sidebar /></div><div className="min-w-0 flex-1"><MobileNav />{children}</div></div>;
}
