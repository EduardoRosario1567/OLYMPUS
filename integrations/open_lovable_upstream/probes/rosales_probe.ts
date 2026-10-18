import { createHash } from "node:crypto";

const BASE = "http://olympus-lovable-staging.railway.internal:8080";
const MODEL = Bun.env.OLYMPUS_STAGING_GROQ_MODEL || "qwen/qwen3.8-27b";
const TASK = "Crie uma landing page responsiva, elegante e acessível para Rosales Café: café brasileiro com inspiração no estilo colombiano. Use React e CSS sem dependências extras, com cabeçalho, hero, história da marca e chamada para ação. Não invente endereço, preços, depoimentos, notas, contatos ou dados comerciais. Não use imagens externas. Gere código funcional.";

function sha(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

async function post(path, body, headers = {}, deadline = 120000) {
  const response = await fetch(BASE + path, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(deadline),
  });
  if (!response.ok) throw new Error("HTTP_" + response.status);
  const raw = await response.text();
  if (raw.length > 5 * 1024 * 1024) throw new Error("response_too_large");
  if ((response.headers.get("content-type") || "").includes("text/event-stream")) {
    let completed = null, n = 0;
    for (const line of raw.split(/\r?\n/)) {
      if (!line.startsWith("data: ")) continue;
      if (++n > 30000) throw new Error("event_limit");
      let evt;
      try { evt = JSON.parse(line.slice(6)); } catch { throw new Error("invalid_sse"); }
      if (evt.type === "error") throw new Error("upstream_generation_error");
      if (evt.type === "complete") {
        if (completed) throw new Error("duplicate_completion");
        completed = evt;
      }
    }
    if (!completed) throw new Error("no_completion");
    return completed;
  }
  let result;
  try { result = JSON.parse(raw); } catch { throw new Error("invalid_json"); }
  if (!result || result.success === false || result.error) throw new Error("upstream_negative_response");
  return result;
}

async function probe() {
  if (Bun.env.OLYMPUS_ROSALES_PROBE_ONCE !== "1") {
    console.log("OLYMPUS_ROSALES_REAL " + JSON.stringify({ phase: "disabled" }));
    return;
  }
  let phase = "sandbox";
  try {
    const sandbox = await post("/api/create-ai-sandbox-v2", {}, {}, 90000);
    const sid = sandbox.sandboxId;
    if (typeof sid !== "string" || !sid) throw new Error("missing_sandbox_id");
    console.log("OLYMPUS_ROSALES_REAL " + JSON.stringify({ phase, ok: true }));
    phase = "generation";
    const gen = await post("/api/generate-ai-code-stream", {
      prompt: TASK, model: MODEL, context: { sandboxId: sid }, isEdit: false
    }, {}, 180000);
    const source = gen.generatedCode;
    if (typeof source !== "string" || source.length > 2500000 || !source.includes("<file path=")) {
      throw new Error("no_generated_source");
    }
    const proposed = [...source.matchAll(/<file path="([^"]+)">/g)].map(m => m[1]);
    if (!proposed.length || proposed.length > 80) throw new Error("invalid_generated_file_count");
    console.log("OLYMPUS_ROSALES_REAL " + JSON.stringify({ phase, ok: true, model: MODEL, proposedFiles: proposed.length }));
    phase = "apply";
    const applied = await post("/api/apply-ai-code-stream", {
      response: source, isEdit: false, packages: [], sandboxId: sid
    }, {}, 150000);
    const result = applied.results;
    if (!result || (result.errors || []).length) throw new Error("apply_errors");
    const written = new Set([...(result.filesCreated || []), ...(result.filesUpdated || [])]);
    if (!proposed.every(x => written.has(x))) throw new Error("incomplete_apply");
    console.log("OLYMPUS_ROSALES_REAL " + JSON.stringify({ phase, ok: true, written: written.size }));
    phase = "build";
    const build = await post("/api/run-command-v2", { command: "npm run build" }, {}, 120000);
    if (build.success !== true || build.exitCode !== 0 ||
        !/Return code:\s*0\s*$/m.test(String(build.output || ""))) {
      throw new Error("react_build_failed");
    }
    console.log("OLYMPUS_ROSALES_REAL " + JSON.stringify({ phase, ok: true }));
    phase = "export";
    const token = Bun.env.OLYMPUS_BRIDGE_EXPORT_TOKEN;
    if (!token || token.length < 32) throw new Error("export_token_missing");
    const snapshot = await post("/api/olympus-export", { sandboxId: sid },
      { "x-olympus-bridge-token": token }, 120000);
    if (snapshot.sandboxId !== sid || !Array.isArray(snapshot.files) || !snapshot.files.length) {
      throw new Error("snapshot_identity_or_files");
    }
    const files = [...snapshot.files].sort((a,b) =>
      Buffer.compare(Buffer.from(String(a.path)), Buffer.from(String(b.path))));
    const aggregate = createHash("sha256");
    const seen = new Set();
    for (const f of files) {
      if (typeof f.path !== "string" || typeof f.content !== "string" || seen.has(f.path)) {
        throw new Error("malformed_snapshot");
      }
      seen.add(f.path);
      const fileHash = sha(Buffer.from(f.content, "utf8"));
      if (fileHash !== f.sha256) throw new Error("snapshot_file_hash_mismatch");
      aggregate.update(Buffer.from(f.path, "utf8"));
      aggregate.update(Buffer.from([0]));
      aggregate.update(Buffer.from(fileHash, "hex"));
    }
    if (aggregate.digest("hex") !== snapshot.sha256 || !proposed.every(p=>seen.has(p))) {
      throw new Error("snapshot_manifest_mismatch");
    }
    console.log("OLYMPUS_ROSALES_REAL " + JSON.stringify({
      phase:"export", ok:true, model:MODEL, exportedFiles:files.length,
      sha256:snapshot.sha256, result:"BUILT_AND_EXPORTED_BROWSER_REVIEW_PENDING"
    }));
  } catch (err) {
    console.error("OLYMPUS_ROSALES_REAL " + JSON.stringify({
      phase, ok:false, model:MODEL,
      reason: err instanceof Error ? err.message.slice(0,100) : "unknown"
    }));
  }
}
void probe();
export default { fetch() { return new Response("private staging probe", {status:200}); } };
