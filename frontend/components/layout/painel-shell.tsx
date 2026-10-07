import type { ReactNode } from "react";
import { MobileNav, Sidebar } from "./sidebar";

export function PainelShell({ children }: { children: ReactNode }) {
  return <div className="app-shell min-h-screen md:h-screen md:overflow-hidden md:flex"><div className="hidden md:block md:h-screen md:shrink-0"><Sidebar /></div><div className="min-w-0 flex-1 md:h-screen md:overflow-y-auto md:overscroll-contain"><MobileNav />{children}</div></div>;
}
