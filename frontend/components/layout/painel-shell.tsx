import type { ReactNode } from "react";
import { Sidebar } from "./sidebar";

export function PainelShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1">{children}</div>
    </div>
  );
}
