import type { ReactNode } from "react";
import { MobileNav, Sidebar } from "./sidebar";

export function PainelShell({ children }: { children: ReactNode }) {
  return <div className="app-shell app-frame">
    <a className="skip-content" href="#app-content">Ir para o conteúdo</a>
    <div className="app-sidebar hidden md:block"><Sidebar /></div>
    <div className="app-workspace"><MobileNav /><div id="app-content" className="app-content" tabIndex={-1}>{children}</div></div>
  </div>;
}
