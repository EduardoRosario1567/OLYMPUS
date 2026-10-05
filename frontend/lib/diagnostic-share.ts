const SECRET_PATTERNS: Array<[RegExp, string]> = [
  [/"([A-Za-z_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|SENHA)[A-Za-z_]*|authorization|cookie|set-cookie)"\s*:\s*"(?:\\.|[^"\\])*"/gi, '"$1": "[REDACTED]"'],
  [/\b(Bearer)\s+[A-Za-z0-9._~+\/-]+=*/gi, "$1 [REDACTED]"],
  [/\b(sk-[A-Za-z0-9_-]{12,})\b/g, "[REDACTED_API_KEY]"],
  [/\bAIza[A-Za-z0-9_-]{20,}\b/g, "[REDACTED_API_KEY]"],
  [/\b(gsk_[A-Za-z0-9_-]{12,})\b/g, "[REDACTED_API_KEY]"],
  [/\b([A-Za-z_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|SENHA)[A-Za-z_]*)\s*[:=]\s*([^\s,;]+)/gi, "$1=[REDACTED]"],
  [/\b(authorization|cookie|set-cookie)\s*:\s*[^\n]+/gi, "$1: [REDACTED]"],
];

export function selectDiagnosticEvents<T extends { event: string }>(events: T[], limit = 80): T[] {
  const essential = new Set(["mission_compiled", "routing_policy_selected", "model_selected",
    "model_resume", "model_failover", "worker_requeued", "failed", "completion_rejected",
    "verification_started", "verification_completed", "result_published", "step_blocked",
    "mission_stop", "mission_end", "finished"]);
  const selected = new Set(events.filter(event => essential.has(event.event)));
  // Initial contract, all failovers and rejection evidence outrank repeated
  // advisory-context events. If essentials exceed the display limit retain
  // them all rather than silently losing the cause of a long mission.
  for (const event of events.slice().reverse()) {
    if (selected.size >= limit) break;
    selected.add(event);
  }
  return events.filter(event => selected.has(event));
}

export function sanitizeDiagnostic(value: string): string {
  let text = String(value ?? "");
  for (const [pattern, replacement] of SECRET_PATTERNS) text = text.replace(pattern, replacement);
  return text;
}

export async function copyDiagnostic(value: string): Promise<void> {
  const text = sanitizeDiagnostic(value);
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "true");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

export function downloadDiagnostic(value: string, filename = "olympus-diagnostic.txt"): void {
  const blob = new Blob([sanitizeDiagnostic(value)], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function shareDiagnostic(value: string): Promise<"shared" | "copied"> {
  const text = sanitizeDiagnostic(value);
  if (navigator.share) {
    await navigator.share({ title: "Diagnóstico técnico OLYMPUS", text });
    return "shared";
  }
  await copyDiagnostic(text);
  return "copied";
}
