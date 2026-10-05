"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import { copyDiagnostic, downloadDiagnostic, sanitizeDiagnostic, shareDiagnostic } from "@/lib/diagnostic-share";
import olympusVersion from "@/public/olympus-version.json";

function collectPageDiagnostic() {
  const mission = document.querySelector<HTMLElement>(".mission-diagnostic");
  const body = mission?.dataset.diagnosticText ?? mission?.textContent ?? document.body?.innerText ?? "";
  const header = [
    `OLYMPUS ${olympusVersion.version}`,
    `URL: ${window.location.href}`,
    `Data: ${new Date().toISOString()}`,
    "",
  ].join("\n");
  return sanitizeDiagnostic(header + body);
}

export function DiagnosticActions() {
  const [notice, setNotice] = useState("");

  async function copy() {
    await copyDiagnostic(collectPageDiagnostic());
    setNotice("Diagnóstico copiado");
    window.setTimeout(() => setNotice(""), 1800);
  }
  async function share() {
    try {
      const mode = await shareDiagnostic(collectPageDiagnostic());
      setNotice(mode === "shared" ? "Compartilhado" : "Copiado para compartilhar");
    } catch {
      setNotice("Compartilhamento cancelado");
    }
    window.setTimeout(() => setNotice(""), 1800);
  }

  return <span role="toolbar" aria-label="Diagnóstico técnico" className="inline-flex flex-wrap items-center gap-2 font-sans" onClick={(event) => { event.preventDefault(); event.stopPropagation(); }}>
    <button type="button" onClick={() => void copy()} style={{ background: "var(--app-panel)", color: "var(--app-text)", borderColor: "var(--app-border)" }} className="rounded-lg border px-3 py-2 text-xs hover:opacity-80">Copiar diagnóstico</button>
    <button type="button" onClick={() => downloadDiagnostic(collectPageDiagnostic(), `olympus-diagnostic-${Date.now()}.txt`)} style={{ background: "var(--app-panel)", color: "var(--app-text)", borderColor: "var(--app-border)" }} className="rounded-lg border px-3 py-2 text-xs hover:opacity-80">Baixar diagnóstico</button>
    <button type="button" onClick={() => void share()} style={{ background: "var(--app-text)", color: "var(--app-bg)" }} className="rounded-lg px-3 py-2 text-xs font-medium hover:opacity-90">Compartilhar detalhes</button>
    {notice && <span role="status" className="px-1 text-[11px] text-emerald-600 dark:text-emerald-300">{notice}</span>}
  </span>;
}

export function TechnicalShareTools() {
  const pathname = usePathname();
  if (pathname !== "/logs") return null;

  return <div style={{ background: "var(--app-panel)", borderColor: "var(--app-border)" }} className="fixed right-4 top-20 z-[95] rounded-xl border p-2 shadow-lg backdrop-blur">
    <DiagnosticActions />
  </div>;
}
