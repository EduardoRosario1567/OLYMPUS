"use client";

import { FormEvent, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { PainelShell } from "@/components/layout/painel-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type CloudAttachment, type CloudDeployment, type CloudEvent, type CloudExecution, type CloudGitHubCommit, type CloudGitHubStatus, type CloudPreviewSession, type CloudProject, type CloudProjectVersion, type CloudPublication, type CloudRailwayStatus, type CloudRuntimeLog, type CloudSecretReference, type CloudStudioFile, type CloudStudioFileContent, type CloudVersionComparison } from "@/services/api";
import { useRequireAuth } from "@/hooks/useAuth";
import { sanitizeDiagnostic } from "@/lib/diagnostic-share";
import { DiagnosticActions } from "@/components/technical-share-tools";
import { useSearchParams } from "next/navigation";

const TERMINAL = new Set(["completed", "failed", "blocked", "cancelled", "paused_capacity", "waiting_capacity"]);
const LABELS: Record<string, string> = {
  queued: "Preparando sua missão",
  running: "Trabalhando no seu pedido",
  verifying: "Verificando o resultado",
  completed: "Tudo pronto",
  failed: "A missão foi interrompida",
  blocked: "Missão interrompida com diagnóstico",
  cancelled: "Missão cancelada",
  paused_capacity: "Missão pausada por falta de capacidade",
  waiting_capacity: "Missão pausada por falta de capacidade",
};

const EVENT_LABELS: Record<string, string> = {
  queued: "Pedido colocado na fila",
  running: "Trabalho iniciado",
  mission_created: "Pedido recebido",
  execution_started: "Trabalho iniciado",
  planning_started: "Organizando as etapas",
  plan_created: "Plano preparado",
  action_started: "Aplicando as alterações",
  action_completed: "Alteração concluída",
  verification_started: "Conferindo a entrega",
  verification_completed: "Verificação concluída",
  result_published: "Resultado preparado para download",
  execution_completed: "Missão concluída",
  completed: "Missão concluída",
  finished: "Tentativa encerrada",
  model_selected: "Recursos preparados",
  model_failover: "Outra IA selecionada automaticamente",
  model_resume: "Progresso repassado para a próxima IA",
  mission_compiled: "Pedido traduzido para execução",
  routing_policy_selected: "Política de continuidade confirmada",
  worker_requeued: "Nova tentativa preparada",
  resumed: "Missão retomada",
  waiting_for_capacity: "Aguardando uma rota disponível",
  capacity_paused: "Execução pausada; seu progresso foi preservado",
  integration_synced: "Código sincronizado com o GitHub",
  integration_failed: "Entrega local pronta; GitHub aguardando reconexão",
};

const SUGESTOES = [
  {
    label: "Criar do zero",
    detail: "Sites, apps e experiências completas",
    prompt: "Crie uma página web moderna, responsiva e pronta para uso",
    icon: <Icon className="h-[18px] w-[18px]"><path d="M12 3v18M3 12h18" /></Icon>,
  },
  {
    label: "Evoluir um projeto",
    detail: "Melhore visual, conteúdo e experiência",
    prompt: "Analise meu projeto e melhore a interface sem alterar as funções",
    icon: <Icon className="h-[18px] w-[18px]"><path d="m4 16 5-5 4 4 7-8" /><path d="M15 7h5v5" /></Icon>,
  },
  {
    label: "Corrigir problemas",
    detail: "Encontre a causa, repare e verifique",
    prompt: "Analise meu projeto, encontre os erros e corrija com segurança",
    icon: <Icon className="h-[18px] w-[18px]"><path d="m14 6 4-4 4 4-4 4" /><path d="M18 2v8M10 18l-4 4-4-4 4-4" /><path d="M6 22v-8M18 10c0 4.4-3.6 8-8 8H6" /></Icon>,
  },
  {
    label: "Analisar uma ideia",
    detail: "Transforme intenção em plano executável",
    prompt: "Analise esta ideia, identifique riscos e transforme em um plano de construção: ",
    icon: <Icon className="h-[18px] w-[18px]"><path d="M9 18h6M10 22h4" /><path d="M8.5 14.5A7 7 0 1 1 15.5 14.5C14.5 15.3 14 16.2 14 18h-4c0-1.8-.5-2.7-1.5-3.5Z" /></Icon>,
  },
];
const ACCEPTED_FILES = ".txt,.md,.csv,.json,.yaml,.yml,.xml,.html,.htm,.css,.js,.jsx,.ts,.tsx,.py,.sh,.sql,.pdf,.docx,.xlsx,.png,.jpg,.jpeg,.webp,.gif,.zip";

function Icon({ children, className = "h-5 w-5" }: { children: ReactNode; className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">{children}</svg>;
}

function OlympusMark({ className = "h-8 w-8" }: { className?: string }) {
  return <span className={`${className} olympus-mark shrink-0 bg-contain bg-center bg-no-repeat`} style={{ backgroundImage: "url('/olympus-mark.png?v=2.6.2')" }} aria-hidden="true" />;
}

function formatarTempo(segundos: number) {
  const minutos = String(Math.floor(segundos / 60)).padStart(2, "0");
  const restantes = String(segundos % 60).padStart(2, "0");
  return `${minutos}:${restantes}`;
}

function mensagemAmigavel(error?: string | null) {
  if (!error) return null;
  const value = error.toLowerCase();
  if (value.includes("free-models-per-day") || value.includes("daily quota") || value.includes("daily limit")) return "A cota diária desta IA terminou e não há outra rota gratuita independente configurada. Seu projeto foi preservado.";
  if (value.includes("connection refused") || value.includes("network") || value.includes("urlopen")) return "Não consegui alcançar o serviço de execução. Aguarde alguns segundos e retome a missão.";
  if (value.includes("unavailable for free") || value.includes("model") || value.includes("404")) return "A rota escolhida ficou indisponível. O Olympus pode selecionar outra automaticamente ao retomar.";
  if (value.includes("malformed action") || value.includes("target is required")) return "Recebi uma instrução incompleta e interrompi a execução para proteger seu projeto.";
  if (value.includes("completion_validation")) return "A página não foi criada corretamente e, por segurança, o Olympus não publicou um resultado vazio.";
  if (value.includes("missão em andamento")) return "Este projeto já possui uma missão em andamento. Aguarde a conclusão antes de iniciar outra.";
  return "A missão foi interrompida antes da entrega. Consulte o diagnóstico técnico abaixo e só retome depois de corrigir a causa.";
}

export default function MissaoPage() {
  const pronto = useRequireAuth();
  const searchParams = useSearchParams();
  const requestedProjectId = searchParams.get("project_id");
  const [projects, setProjects] = useState<CloudProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [task, setTask] = useState("");
  const [submittedTask, setSubmittedTask] = useState("");
  const [attachments, setAttachments] = useState<CloudAttachment[]>([]);
  const [submittedAttachments, setSubmittedAttachments] = useState<CloudAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [execution, setExecution] = useState<CloudExecution | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [events, setEvents] = useState<CloudEvent[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [paidFallback, setPaidFallback] = useState(false);
  const [paidSpendCap, setPaidSpendCap] = useState(1);
  const [workspacePanel, setWorkspacePanel] = useState<"preview" | "files" | "versions" | "publish" | null>(null);
  const [preview, setPreview] = useState<CloudPreviewSession | null>(null);
  const [versions, setVersions] = useState<CloudProjectVersion[]>([]);
  const [comparison, setComparison] = useState<CloudVersionComparison | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [panelNotice, setPanelNotice] = useState<string | null>(null);
  const [studioFiles, setStudioFiles] = useState<CloudStudioFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<CloudStudioFileContent | null>(null);
  const [fileDraft, setFileDraft] = useState("");
  const [runtimeLogs, setRuntimeLogs] = useState<CloudRuntimeLog[]>([]);
  const latestSeq = useRef(0);
  const runtimeSeq = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const executionId = execution?.execution_id;
  const executionStatus = execution?.status;

  useEffect(() => {
    if (!pronto) return;
    api.listarCloudProjetos().then((items) => {
      setProjects(items);
      const selected = items.find((item) => item.project_id === requestedProjectId) ?? (requestedProjectId ? undefined : items[0]);
      if (selected) {
        setProjectId(selected.project_id);
        setErro(null);
      } else if (requestedProjectId) {
        setProjectId("");
        setErro("O projeto selecionado não foi encontrado.");
      } else {
        setProjectId("");
        setErro("Crie um projeto na pasta Projetos da barra lateral para começar.");
      }
    }).catch(() => setErro("Não consegui carregar seus projetos agora."));
  }, [pronto, requestedProjectId]);

  useEffect(() => {
    if (!pronto || !projectId) return;
    setExecution(null);
    setSubmittedTask("");
    setSubmittedAttachments([]);
    setEvents([]);
    setStartedAt(null);
    setElapsed(0);
    setWorkspacePanel(null);
    setPreview(null);
    setVersions([]);
    setComparison(null);
    setSelectedVersion(null);
    setStudioFiles([]);
    setSelectedFile(null);
    setRuntimeLogs([]);
    latestSeq.current = 0;
    runtimeSeq.current = 0;
    let stopped = false;
    const hydrateLatestExecution = async () => {
      try {
        const items = await api.listarCloudExecucoes({ project_id: projectId, limit: 1 });
        if (stopped) return;
        const latest = items[0];
        if (!latest) return;
        setExecution((current) => {
          if (current?.project_id === projectId && current.updated_at >= latest.updated_at) return current;
          return latest;
        });
        setSubmittedTask(latest.task.split("\n\n[OLYMPUS_ATTACHMENTS]")[0]);
        setStartedAt(latest.created_at ? latest.created_at * 1000 : Date.now());
        latestSeq.current = 0;
        try {
          const history = await api.listarCloudEventos(latest.execution_id, 0);
          if (!stopped) {
            setEvents(history.events);
            if (history.events.length) latestSeq.current = history.events[history.events.length - 1].seq;
          }
        } catch { /* Histórico é auxiliar; a execução continua visível sem ele. */ }
      } catch { /* Um projeto sem execução anterior é normal. */ }
    };
    void hydrateLatestExecution();
    return () => { stopped = true; };
  }, [pronto, projectId]);

  useEffect(() => {
    if (!startedAt || !executionStatus || TERMINAL.has(executionStatus)) return;
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 250);
    return () => window.clearInterval(id);
  }, [startedAt, executionStatus]);

  useEffect(() => {
    if (!executionId || !executionStatus || TERMINAL.has(executionStatus)) return;
    let stopped = false;
    const poll = async () => {
      try {
        const latest = await api.obterCloudExecucao(executionId);
        const data = await api.listarCloudEventos(executionId, latestSeq.current);
        if (stopped) return;
        setExecution(latest);
        if (data.events.length) {
          latestSeq.current = data.events[data.events.length - 1].seq;
          setEvents((old) => [...old, ...data.events]);
        }
      } catch (error) {
        if (!stopped) setErro(error instanceof ApiError ? mensagemAmigavel(error.message) : "Não consegui acompanhar a missão agora.");
      }
    };
    void poll();
    const id = window.setInterval(poll, 1200);
    return () => { stopped = true; window.clearInterval(id); };
  }, [executionId, executionStatus]);

  useEffect(() => {
    if (workspacePanel !== "preview" || !projectId || preview?.kind !== "runtime") return;
    let stopped = false;
    const poll = async () => {
      try {
        const fresh = await api.listarCloudRuntimeLogs(projectId, runtimeSeq.current);
        if (!stopped && fresh.length) {
          runtimeSeq.current = fresh[fresh.length - 1].seq;
          setRuntimeLogs((old) => [...old, ...fresh].slice(-300));
        }
      } catch { /* O preview pode ter sido encerrado entre duas consultas. */ }
    };
    void poll();
    const id = window.setInterval(poll, 1500);
    return () => { stopped = true; window.clearInterval(id); };
  }, [workspacePanel, projectId, preview?.kind]);

  const statusText = useMemo(() => execution ? LABELS[execution.status] ?? "Trabalhando no seu pedido" : "", [execution]);
  const selectedProject = useMemo(() => projects.find((project) => project.project_id === projectId), [projects, projectId]);
  const emAndamento = Boolean(execution && !TERMINAL.has(execution.status));
  const podeRetomar = execution?.status === "blocked" || execution?.status === "cancelled" || execution?.status === "failed" || execution?.status === "paused_capacity" || execution?.status === "waiting_capacity";

  async function executar(e?: FormEvent) {
    e?.preventDefault();
    if (!projectId || !task.trim() || emAndamento) return;
    setErro(null); setSending(true); setEvents([]); setElapsed(0); latestSeq.current = 0;
    try {
      const cleanTask = task.trim();
      const created = await api.criarCloudMissao({
        project_id: projectId,
        task: cleanTask,
        max_iterations: 24,
        attachment_ids: attachments.map((item) => item.attachment_id),
        routing_mode: paidFallback ? "protected" : "free_first",
        paid_fallback_authorized: paidFallback,
        paid_spend_cap_usd: paidFallback ? paidSpendCap : 0,
      });
      setSubmittedTask(cleanTask); setSubmittedAttachments(attachments); setTask(""); setAttachments([]); setExecution(created); setStartedAt(Date.now());
    } catch (error) {
      const friendly = error instanceof ApiError ? mensagemAmigavel(error.message) : "Não consegui iniciar a missão.";
      setErro(friendly);
      if (error instanceof ApiError && error.message.toLowerCase().includes("missão em andamento")) {
        try {
          const active = await api.listarCloudExecucoes({ project_id: projectId, limit: 1 });
          if (active[0]) {
            setExecution(active[0]);
            setSubmittedTask(active[0].task.split("\n\n[OLYMPUS_ATTACHMENTS]")[0]);
            setStartedAt(active[0].created_at ? active[0].created_at * 1000 : Date.now());
            const history = await api.listarCloudEventos(active[0].execution_id, 0);
            setEvents(history.events);
            if (history.events.length) latestSeq.current = history.events[history.events.length - 1].seq;
          }
        } catch { /* Mantém a mensagem original se a recuperação não responder. */ }
      }
    } finally { setSending(false); }
  }

  async function cancelar() {
    if (!execution) return;
    try { setExecution(await api.cancelarCloudExecucao(execution.execution_id)); }
    catch { setErro("Não consegui cancelar a missão agora."); }
  }

  async function retomar() {
    if (!execution) return;
    try {
      const resumed = await api.retomarCloudExecucao(execution.execution_id);
      setExecution(resumed); setStartedAt(Date.now()); setErro(null);
    } catch { setErro("Não consegui retomar a missão agora."); }
  }

  async function baixarResultado() {
    if (!execution) return;
    try { await api.baixarCloudProjeto(execution.project_id); setErro(null); }
    catch { setErro("O resultado está pronto, mas o download não iniciou. Tente novamente."); }
  }

  async function abrirPreview() {
    if (!projectId) return;
    setWorkspacePanel("preview"); setPanelLoading(true); setPanelError(null); setPanelNotice(null); setRuntimeLogs([]); runtimeSeq.current = 0;
    try { setPreview(await api.criarCloudPreview(projectId)); }
    catch (error) { setPreview(null); setPanelError(error instanceof ApiError ? error.message : "Não consegui preparar o preview."); }
    finally { setPanelLoading(false); }
  }

  async function carregarVersoes() {
    if (!projectId) return;
    setWorkspacePanel("versions"); setPanelLoading(true); setPanelError(null); setPanelNotice(null); setComparison(null); setSelectedVersion(null);
    try { setVersions(await api.listarCloudVersoes(projectId)); }
    catch { setPanelError("Não consegui carregar o histórico de versões."); }
    finally { setPanelLoading(false); }
  }

  async function carregarArquivos() {
    if (!projectId) return;
    setWorkspacePanel("files"); setPanelLoading(true); setPanelError(null); setPanelNotice(null);
    try {
      const files = await api.listarCloudArquivos(projectId);
      setStudioFiles(files);
      if (!selectedFile && files.length) await abrirArquivo(files[0].path);
    } catch { setPanelError("Não consegui carregar os arquivos editáveis deste projeto."); }
    finally { setPanelLoading(false); }
  }

  function abrirPublicacao() {
    if (!projectId) return;
    setWorkspacePanel("publish"); setPanelError(null); setPanelNotice(null);
  }

  async function abrirArquivo(path: string) {
    if (!projectId) return;
    setPanelLoading(true); setPanelError(null); setPanelNotice(null);
    try {
      const file = await api.abrirCloudArquivo(projectId, path);
      setSelectedFile(file); setFileDraft(file.content);
    } catch { setPanelError("Não consegui abrir este arquivo com segurança."); }
    finally { setPanelLoading(false); }
  }

  async function salvarArquivo() {
    if (!projectId || !selectedFile || fileDraft === selectedFile.content || panelLoading) return;
    setPanelLoading(true); setPanelError(null); setPanelNotice(null);
    try {
      const saved = await api.salvarCloudArquivo(projectId, selectedFile.path, fileDraft, selectedFile.sha256);
      setSelectedFile(saved);
      setStudioFiles(await api.listarCloudArquivos(projectId));
      setPreview(null);
      setPanelNotice("Arquivo salvo. Uma versão de segurança foi criada automaticamente.");
    } catch (error) { setPanelError(error instanceof ApiError ? error.message : "Não consegui salvar este arquivo."); }
    finally { setPanelLoading(false); }
  }

  async function salvarVersao() {
    if (!projectId || panelLoading) return;
    const label = window.prompt("Nome desta versão", "Versão salva manualmente");
    if (label === null) return;
    setPanelLoading(true); setPanelError(null); setPanelNotice(null);
    try {
      await api.criarCloudVersao(projectId, label.trim().slice(0, 100) || "Versão salva manualmente");
      setVersions(await api.listarCloudVersoes(projectId));
      setPanelNotice("Versão atual salva com segurança.");
    } catch { setPanelError("Não consegui salvar esta versão."); }
    finally { setPanelLoading(false); }
  }

  async function compararVersao(versionId: string) {
    if (!projectId) return;
    setSelectedVersion(versionId); setPanelLoading(true); setPanelError(null); setPanelNotice(null);
    try { setComparison(await api.compararCloudVersao(projectId, versionId)); }
    catch { setComparison(null); setPanelError("Não consegui comparar esta versão."); }
    finally { setPanelLoading(false); }
  }

  async function restaurarVersao(version: CloudProjectVersion) {
    if (!projectId || panelLoading) return;
    const confirmed = window.confirm(`Restaurar “${version.label}”? O Olympus salvará automaticamente o estado atual antes da restauração.`);
    if (!confirmed) return;
    setPanelLoading(true); setPanelError(null); setPanelNotice(null);
    try {
      const result = await api.restaurarCloudVersao(projectId, version.version_id);
      setVersions(await api.listarCloudVersoes(projectId));
      setComparison(null); setSelectedVersion(null); setPreview(null);
      setPanelNotice(`Versão restaurada. O estado anterior foi preservado em “${result.safety_backup.label}”.`);
    } catch (error) { setPanelError(error instanceof ApiError ? error.message : "A restauração não pôde ser concluída."); }
    finally { setPanelLoading(false); }
  }

  async function enviarArquivos(files: File[]) {
    if (!projectId) {
      setErro("Crie ou escolha um projeto na pasta Projetos da barra lateral antes de anexar arquivos.");
      return;
    }
    const remaining = Math.max(0, 10 - attachments.length);
    const selected = files.slice(0, remaining);
    if (!selected.length) {
      setErro("Você pode enviar até 10 arquivos por missão.");
      return;
    }
    setUploading(true); setErro(null);
    try {
      for (const file of selected) {
        if (file.size > 20 * 1024 * 1024) {
          setErro(`${file.name} excede o limite de 20 MB.`);
          continue;
        }
        try {
          const uploaded = await api.enviarCloudAnexo(projectId, file);
          setAttachments((old) => [...old, uploaded]);
        } catch (error) {
          setErro(error instanceof ApiError ? error.message : `Não consegui enviar ${file.name}.`);
        }
      }
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function removerArquivo(attachment: CloudAttachment) {
    if (emAndamento) return;
    try {
      await api.removerCloudAnexo(attachment.project_id, attachment.attachment_id);
      setAttachments((old) => old.filter((item) => item.attachment_id !== attachment.attachment_id));
    } catch { setErro("Não consegui remover o anexo agora."); }
  }

  function limpar() {
    setExecution(null); setEvents([]); setTask(""); setSubmittedTask(""); setAttachments([]); setSubmittedAttachments([]); setElapsed(0); setStartedAt(null); setErro(null); setWorkspacePanel(null); setPreview(null); setStudioFiles([]); setSelectedFile(null); setFileDraft(""); setRuntimeLogs([]); latestSeq.current = 0; runtimeSeq.current = 0;
  }

  if (!pronto) return null;

  const composer = <>
    {erro && <div className="mb-2 flex items-start justify-between gap-3 rounded-xl bg-[#2a1719] px-4 py-3 text-sm text-rose-200"><span>{erro}</span><button type="button" onClick={() => setErro(null)} aria-label="Fechar aviso" className="text-rose-300/60 hover:text-rose-100">×</button></div>}
    <form onSubmit={executar} onDragEnter={(e) => { e.preventDefault(); if (!emAndamento) setDragging(true); }} onDragOver={(e) => e.preventDefault()} onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }} onDrop={(e) => { e.preventDefault(); setDragging(false); if (!emAndamento) void enviarArquivos(Array.from(e.dataTransfer.files)); }} className={`composer-shell rounded-[26px] border p-2.5 shadow-2xl ${dragging ? "border-cyan-300/50" : "border-white/[0.1]"}`}>
      <input ref={fileInput} type="file" multiple accept={ACCEPTED_FILES} className="hidden" onChange={(e) => void enviarArquivos(Array.from(e.target.files ?? []))} />
      {(attachments.length > 0 || uploading) && <div className="flex flex-wrap gap-2 px-2 pb-1 pt-1">{attachments.map((attachment) => <AttachmentChip key={attachment.attachment_id} attachment={attachment} removable={!emAndamento} onRemove={() => void removerArquivo(attachment)} />)}{uploading && <span className="flex items-center gap-2 rounded-xl bg-white/[0.055] px-3 py-2 text-xs text-zinc-400"><span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300" />Enviando...</span>}</div>}
      <textarea value={task} onChange={(e) => setTask(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} disabled={emAndamento} maxLength={4000} rows={2} placeholder="Peça alguma coisa ao Olympus — crie, corrija ou evolua seu projeto" className="max-h-40 min-h-[64px] w-full resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-zinc-100 outline-none placeholder:text-zinc-500 disabled:opacity-50" />
      <div className="composer-toolbar flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] px-1 pt-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {!emAndamento && <button type="button" onClick={() => fileInput.current?.click()} disabled={uploading} className="composer-tool" aria-label="Anexar arquivos"><Icon className="h-4 w-4"><path d="M12 5v14M5 12h14" /></Icon><span className="hidden sm:inline">Anexar</span></button>}
          {selectedProject && <span className="hidden max-w-[190px] truncate rounded-xl border border-white/[0.07] px-3 py-2 text-xs text-zinc-500 lg:inline" title="Projeto selecionado na pasta Projetos">{selectedProject.name}</span>}
        </div>
        <div className="flex items-center gap-2">
          {!emAndamento && <label className="composer-paid flex items-center gap-2 rounded-xl px-2.5 py-2 text-[11px] text-zinc-500"><input type="checkbox" checked={paidFallback} onChange={(event) => setPaidFallback(event.target.checked)} className="h-3.5 w-3.5 accent-cyan-500" /><span className="hidden md:inline">IA paga se necessário</span>{paidFallback && <><span className="hidden lg:inline">· teto US$</span><input aria-label="Limite de gasto da missão" type="number" min={0.1} max={1000} step={0.1} value={paidSpendCap} onChange={(event) => setPaidSpendCap(Math.max(0.1, Number(event.target.value) || 0.1))} className="w-14 rounded-md border border-white/[0.08] bg-transparent px-1.5 py-1 text-zinc-300 outline-none" /></>}</label>}
          <button type="submit" disabled={sending || uploading || emAndamento || !projectId || !task.trim()} aria-label="Enviar pedido" className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-black transition hover:scale-[1.03] hover:bg-zinc-200 disabled:scale-100 disabled:bg-zinc-700 disabled:text-zinc-500"><Icon className="h-[18px] w-[18px]"><path d="M12 19V5M6 11l6-6 6 6" /></Icon></button>
        </div>
      </div>
    </form>
    <p className="mt-2 flex items-center justify-center gap-1.5 text-[10px] text-zinc-700"><Icon className="h-3 w-3"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>Checkpoint e versão de segurança automáticos</p>
  </>;

  return <PainelShell>
    <main className="relative flex min-h-[calc(100vh-4rem)] flex-col md:min-h-screen">
      <header className="project-bar sticky top-16 z-40 flex min-h-[68px] items-center justify-between gap-3 border-b border-white/[0.06] px-4 backdrop-blur-xl md:top-0 sm:px-6">
        <button type="button" onClick={limpar} className="flex min-w-0 items-center gap-3 rounded-xl py-1.5 text-left transition hover:opacity-80">
          <span className="project-icon grid h-9 w-9 shrink-0 place-items-center rounded-xl"><Icon className="h-[18px] w-[18px]"><path d="M4 7h6l2 2h8v10H4z" /><path d="M4 7V5h6l2 2h5" /></Icon></span>
          <span className="min-w-0"><span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-600">Projeto atual</span><span className="block max-w-[260px] truncate text-sm font-semibold text-zinc-100 sm:max-w-[420px]">{selectedProject?.name ?? "Escolha um projeto"}</span></span>
        </button>
        <div className="flex items-center gap-1.5">
          {projectId && !emAndamento && <><button type="button" onClick={abrirPreview} className="project-action flex"><Icon className="h-4 w-4"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="2.5" /></Icon><span className="hidden lg:inline">Visualizar</span></button><button type="button" onClick={carregarArquivos} className="project-action hidden sm:flex"><Icon className="h-4 w-4"><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v5h5" /></Icon><span className="hidden lg:inline">Arquivos</span></button><button type="button" onClick={carregarVersoes} className="project-action hidden sm:flex"><Icon className="h-4 w-4"><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6" /><path d="M4 4v4.6h4.6" /></Icon><span className="hidden lg:inline">Versões</span></button><button type="button" onClick={abrirPublicacao} className="project-action project-action-primary flex"><Icon className="h-4 w-4"><path d="M12 16V4M7 9l5-5 5 5" /><path d="M5 14v6h14v-6" /></Icon><span className="hidden lg:inline">Publicar</span></button></>}
          {emAndamento && <button type="button" onClick={cancelar} className="project-action flex text-rose-300"><Icon className="h-4 w-4"><rect x="7" y="7" width="10" height="10" rx="1" /></Icon><span className="hidden sm:inline">Interromper</span></button>}
        </div>
      </header>

      {!execution ? <EmptyState onSelect={setTask} composer={composer} /> : <><div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pb-44 sm:px-6"><Conversation task={submittedTask || execution.task.split("\n\n[OLYMPUS_ATTACHMENTS]")[0]} attachments={submittedAttachments} execution={execution} statusText={statusText} elapsed={elapsed} events={events} emAndamento={emAndamento} podeRetomar={podeRetomar} onResume={retomar} onDownload={baixarResultado} onPreview={abrirPreview} onVersions={carregarVersoes} onNew={limpar} /></div><div className="composer-dock fixed inset-x-0 bottom-0 z-30 px-3 pb-4 pt-10 md:left-[252px] sm:px-6"><div className="mx-auto max-w-3xl">{composer}</div></div></>}
    </main>
    {workspacePanel && <WorkspaceOverlay projectId={projectId} mode={workspacePanel} preview={preview} versions={versions} comparison={comparison} selectedVersion={selectedVersion} files={studioFiles} selectedFile={selectedFile} fileDraft={fileDraft} runtimeLogs={runtimeLogs} loading={panelLoading} error={panelError} notice={panelNotice} task={task} execution={execution} statusText={statusText} events={events} emAndamento={emAndamento} sending={sending} onTask={setTask} onStart={() => void executar()} onMode={(mode) => mode === "preview" ? void abrirPreview() : mode === "files" ? void carregarArquivos() : mode === "versions" ? void carregarVersoes() : abrirPublicacao()} onClose={() => setWorkspacePanel(null)} onReload={() => void abrirPreview()} onDownload={() => void baixarResultado()} onSaveVersion={() => void salvarVersao()} onCompare={(versionId) => void compararVersao(versionId)} onRestore={(version) => void restaurarVersao(version)} onOpenFile={(path) => void abrirArquivo(path)} onDraft={setFileDraft} onSaveFile={() => void salvarArquivo()} onElement={(element) => { setTask(`Altere o elemento ${element.selector}${element.text ? ` (“${element.text}”)` : ""}: `); if (window.innerWidth < 768) setWorkspacePanel(null); }} />}
  </PainelShell>;
}

function EmptyState({ onSelect, composer }: { onSelect: (value: string) => void; composer: ReactNode }) {
  return <section className="olympus-welcome relative mx-auto flex w-full max-w-4xl flex-1 flex-col items-center overflow-hidden px-4 pb-8 pt-7 text-center sm:px-6 sm:pt-9">
    <div className="olympus-aura" aria-hidden="true" />
    <div className="relative z-10 flex w-full flex-col items-center">
      <div className="olympus-hero-mark"><OlympusMark className="h-11 w-11" /></div>
      <h1 className="mt-4 text-3xl font-semibold tracking-[-0.045em] text-zinc-50 sm:text-[38px] sm:leading-[1.08]">O que vamos construir hoje?</h1>
      <p className="mt-3 flex max-w-xl items-center justify-center gap-2 text-sm leading-6 text-zinc-500"><span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.65)]" />Olympus pronto para planejar, construir e verificar seu projeto.</p>
      <div className="welcome-composer mt-6 w-full max-w-3xl text-left">{composer}</div>
      <div className="mt-5 flex w-full max-w-3xl items-center gap-3"><span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-zinc-600">Comece com um atalho</span><span className="welcome-divider h-px flex-1" /></div>
      <div className="mt-3 grid w-full max-w-3xl gap-2 sm:grid-cols-2">{SUGESTOES.map((sugestao) => <button key={sugestao.label} type="button" onClick={() => onSelect(sugestao.prompt)} className="olympus-action-card group flex items-center gap-3 rounded-2xl border border-white/[0.075] bg-white/[0.018] px-3.5 py-3 text-left transition duration-200 hover:-translate-y-0.5 hover:border-cyan-200/[0.16] hover:bg-white/[0.04]">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-white/[0.07] bg-black/20 text-zinc-500 transition group-hover:border-cyan-200/[0.12] group-hover:text-cyan-200/80">{sugestao.icon}</span>
        <span className="min-w-0"><span className="block text-sm font-medium text-zinc-300 transition group-hover:text-zinc-50">{sugestao.label}</span><span className="mt-0.5 block text-[11px] leading-4 text-zinc-600 transition group-hover:text-zinc-500">{sugestao.detail}</span></span>
        <Icon className="ml-auto h-4 w-4 shrink-0 text-zinc-700 transition group-hover:translate-x-0.5 group-hover:text-zinc-400"><path d="m9 18 6-6-6-6" /></Icon>
      </button>)}</div>
    </div>
  </section>;
}

function AttachmentChip({ attachment, removable = false, onRemove }: { attachment: CloudAttachment; removable?: boolean; onRemove?: () => void }) {
  const labels = { image: "Imagem", document: "Documento", archive: "Projeto", text: "Arquivo" };
  return <span className="flex max-w-[240px] items-center gap-2 rounded-xl border border-white/[0.07] bg-white/[0.045] px-3 py-2"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white/[0.06] text-zinc-400"><Icon className="h-4 w-4"><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v5h5" /></Icon></span><span className="min-w-0"><span className="block truncate text-xs text-zinc-300">{attachment.name}</span><span className="block text-[10px] text-zinc-600">{labels[attachment.kind]}</span></span>{removable && <button type="button" onClick={onRemove} className="ml-1 text-zinc-600 hover:text-zinc-200" aria-label={`Remover ${attachment.name}`}>×</button>}</span>;
}

function Conversation({ task, attachments, execution, statusText, elapsed, events, emAndamento, podeRetomar, onResume, onDownload, onPreview, onVersions, onNew }: { task: string; attachments: CloudAttachment[]; execution: CloudExecution; statusText: string; elapsed: number; events: CloudEvent[]; emAndamento: boolean; podeRetomar: boolean; onResume: () => void; onDownload: () => void; onPreview: () => void; onVersions: () => void; onNew: () => void }) {
  const sucesso = execution.status === "completed";
  const failure = mensagemAmigavel(execution.error);
  const visibleEvents = events.map((event) => EVENT_LABELS[event.event]).filter((label): label is string => Boolean(label)).slice(-5);
  const technicalEvents = events.filter((event) => ["mission_compiled", "routing_policy_selected", "step_start", "model_selected", "model_resume", "model_failover", "worker_requeued", "failed", "skill_selected", "skill_applied", "skill_fallback", "step_end", "step_blocked", "verification_started", "verification_completed", "completion_rejected", "result_published", "mission_stop", "mission_end", "finished"].includes(event.event)).slice(-80);
  const diagnosticText = sanitizeDiagnostic([
    "OLYMPUS 3.0.8 - DIAGNÓSTICO DE EXECUÇÃO",
    `Execução: ${execution.execution_id}`,
    `Status: ${execution.status}`,
    `Erro: ${execution.error ?? ""}`,
    "",
    "Eventos técnicos:",
    ...technicalEvents.map((event) => `${event.event}\n${JSON.stringify(event.payload ?? event, null, 2)}`),
  ].join("\n"));
  return <div className="w-full space-y-8 py-10 sm:py-14">
    <div className="ml-auto max-w-[85%] rounded-3xl bg-[#2f2f2f] px-5 py-3 text-[15px] leading-6 text-zinc-100">{attachments.length > 0 && <div className="mb-3 flex flex-wrap gap-2">{attachments.map((attachment) => <AttachmentChip key={attachment.attachment_id} attachment={attachment} />)}</div>}{task}</div>
    <div className="flex items-start gap-4">
      <OlympusMark />
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex flex-wrap items-center gap-3"><h2 className="font-medium text-zinc-100">{statusText}</h2>{emAndamento && <span className="text-xs tabular-nums text-zinc-600">{formatarTempo(elapsed)}</span>}</div>
        {emAndamento && <div className="mt-4 flex items-center gap-1.5" aria-label="Olympus trabalhando"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-400" /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-500 [animation-delay:150ms]" /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-600 [animation-delay:300ms]" /></div>}
        {visibleEvents.length > 0 && <ol className="mt-4 space-y-2">{visibleEvents.map((label, index) => <li key={`${label}-${index}`} className="flex items-center gap-2 text-sm text-zinc-500"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400/80" />{label}</li>)}</ol>}
        {failure && <p className="mission-failure-message mt-4 max-w-xl text-sm leading-6 text-amber-200/80">{failure}</p>}
        {execution && technicalEvents.length > 0 && <details data-diagnostic-text={diagnosticText} className="mission-diagnostic group/diagnostic mt-4 max-w-3xl rounded-xl border border-white/[0.07] bg-black/20 p-4"><summary className="flex list-none cursor-pointer flex-wrap items-center justify-between gap-3 text-xs font-medium text-zinc-500"><span className="flex shrink-0 items-center gap-2"><span aria-hidden="true" className="text-[10px] transition-transform group-open/diagnostic:rotate-90">▶</span><span>Ver diagnóstico técnico</span></span><DiagnosticActions /></summary><div className="mt-3 space-y-3 font-mono text-[11px] leading-5 text-zinc-500"><p>Execução: <span className="text-zinc-300">{execution.execution_id}</span></p><p>Status: <span className="text-zinc-300">{execution.status}</span></p><pre className="mission-diagnostic-error max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/30 p-3 text-amber-100/70">{execution.error}</pre>{technicalEvents.length > 0 && <div className="max-h-64 space-y-2 overflow-auto">{technicalEvents.map((event, index) => <pre key={`${event.event}-${index}`} className="mission-diagnostic-event whitespace-pre-wrap break-words rounded-lg bg-black/20 p-3"><span className="text-cyan-300/70">{event.event}</span>{"\n"}{JSON.stringify(event.payload ?? event, null, 2)}</pre>)}</div>}</div></details>}
        {sucesso && <p className="mt-3 text-sm leading-6 text-zinc-400">Seu projeto foi atualizado e verificado. O arquivo final está pronto.</p>}
        <div className="mt-5 flex flex-wrap gap-2">
          {podeRetomar && <Button type="button" onClick={onResume}>Retomar após corrigir</Button>}
          {sucesso && <Button type="button" onClick={onPreview}>Visualizar</Button>}
          {sucesso && <Button type="button" onClick={onDownload}>Baixar resultado</Button>}
          {TERMINAL.has(execution.status) && <Button type="button" variant="secondary" onClick={onVersions}>Versões</Button>}
          {TERMINAL.has(execution.status) && <Button type="button" variant="secondary" onClick={onNew}>Nova missão</Button>}
        </div>
      </div>
    </div>
  </div>;
}

function formatarTamanho(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type SelectedElement = { selector: string; tag: string; text: string };

function StudioRail({ task, execution, statusText, events, emAndamento, sending, onTask, onStart }: { task: string; execution: CloudExecution | null; statusText: string; events: CloudEvent[]; emAndamento: boolean; sending: boolean; onTask: (value: string) => void; onStart: () => void }) {
  const visibleEvents = events.map((event) => EVENT_LABELS[event.event]).filter((label): label is string => Boolean(label)).slice(-4);
  return <aside className="hidden min-h-0 flex-col border-r border-white/[0.07] bg-[#141414] md:flex">
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="flex items-center gap-3"><OlympusMark className="h-7 w-7" /><div><p className="text-sm font-medium text-zinc-200">Olympus</p><p className="text-[10px] text-zinc-600">Ambiente de construção</p></div></div>
      <div className="mt-6 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3"><p className="text-xs font-medium text-zinc-300">{execution ? statusText : "Pronto para a próxima alteração"}</p>{visibleEvents.length > 0 && <div className="mt-3 space-y-1.5">{visibleEvents.map((label, index) => <p key={`${label}-${index}`} className="text-[11px] text-zinc-600">• {label}</p>)}</div>}</div>
    </div>
    <div className="border-t border-white/[0.07] p-3">
      <textarea value={task} onChange={(event) => onTask(event.target.value)} disabled={emAndamento} rows={4} maxLength={4000} placeholder="Peça uma alteração neste projeto" className="w-full resize-none rounded-xl border border-white/[0.08] bg-[#202020] px-3 py-2.5 text-xs leading-5 text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-white/[0.16] disabled:opacity-50" />
      <button type="button" onClick={onStart} disabled={sending || emAndamento || !task.trim()} className="mt-2 w-full rounded-lg bg-white px-3 py-2 text-xs font-medium text-black hover:bg-zinc-200 disabled:bg-zinc-700 disabled:text-zinc-500">{emAndamento ? "Olympus trabalhando" : "Enviar ao Olympus"}</button>
    </div>
  </aside>;
}

function WorkspaceOverlay({ projectId, mode, preview, versions, comparison, selectedVersion, files, selectedFile, fileDraft, runtimeLogs, loading, error, notice, task, execution, statusText, events, emAndamento, sending, onTask, onStart, onMode, onClose, onReload, onDownload, onSaveVersion, onCompare, onRestore, onOpenFile, onDraft, onSaveFile, onElement }: { projectId: string; mode: "preview" | "files" | "versions" | "publish"; preview: CloudPreviewSession | null; versions: CloudProjectVersion[]; comparison: CloudVersionComparison | null; selectedVersion: string | null; files: CloudStudioFile[]; selectedFile: CloudStudioFileContent | null; fileDraft: string; runtimeLogs: CloudRuntimeLog[]; loading: boolean; error: string | null; notice: string | null; task: string; execution: CloudExecution | null; statusText: string; events: CloudEvent[]; emAndamento: boolean; sending: boolean; onTask: (value: string) => void; onStart: () => void; onMode: (mode: "preview" | "files" | "versions" | "publish") => void; onClose: () => void; onReload: () => void; onDownload: () => void; onSaveVersion: () => void; onCompare: (versionId: string) => void; onRestore: (version: CloudProjectVersion) => void; onOpenFile: (path: string) => void; onDraft: (value: string) => void; onSaveFile: () => void; onElement: (element: SelectedElement) => void }) {
  const [viewport, setViewport] = useState<"desktop" | "mobile">("desktop");
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [inspectMode, setInspectMode] = useState(false);
  const [picked, setPicked] = useState<SelectedElement | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const fileDirty = Boolean(selectedFile && fileDraft !== selectedFile.content);
  const confirmDiscard = () => !fileDirty || window.confirm("Descartar as alterações ainda não salvas?");
  const changeMode = (next: "preview" | "files" | "versions" | "publish") => { if (next === mode || confirmDiscard()) onMode(next); };
  const startMission = () => { if (!confirmDiscard()) return; if (fileDirty && selectedFile) onDraft(selectedFile.content); onStart(); };
  const reasonLabels: Record<string, string> = { mission: "Missão concluída", pre_publish: "Backup automático", pre_restore: "Proteção de restauração", pre_edit: "Backup do editor", editor: "Edição manual", manual: "Salva manualmente" };
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      const value = event.data;
      if (event.source !== iframeRef.current?.contentWindow || !value || value.type !== "olympus-element-selected" || typeof value.selector !== "string") return;
      setPicked({ selector: value.selector.slice(0, 500), tag: String(value.tag ?? "elemento").slice(0, 50), text: String(value.text ?? "").slice(0, 160) });
      setInspectMode(false);
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, []);
  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage({ type: "olympus-inspect-mode", enabled: inspectMode }, "*");
  }, [inspectMode]);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && (!fileDirty || window.confirm("Descartar as alterações ainda não salvas?"))) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [fileDirty, onClose]);
  return <div className="fixed inset-0 z-[80] flex bg-black/75 p-2 backdrop-blur-sm sm:p-5" role="dialog" aria-modal="true" aria-label="Ambiente do projeto">
    <section className="mx-auto flex h-full w-full max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-white/[0.1] bg-[#171717] shadow-2xl">
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-white/[0.07] px-3 sm:px-5">
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => changeMode("preview")} className={`rounded-lg px-3 py-2 text-sm ${mode === "preview" ? "bg-white/[0.08] text-white" : "text-zinc-500 hover:text-zinc-200"}`}>Preview</button>
          <button type="button" onClick={() => changeMode("files")} className={`rounded-lg px-3 py-2 text-sm ${mode === "files" ? "bg-white/[0.08] text-white" : "text-zinc-500 hover:text-zinc-200"}`}>Arquivos</button>
          <button type="button" onClick={() => changeMode("versions")} className={`rounded-lg px-3 py-2 text-sm ${mode === "versions" ? "bg-white/[0.08] text-white" : "text-zinc-500 hover:text-zinc-200"}`}>Versões</button>
          <button type="button" onClick={() => changeMode("publish")} className={`rounded-lg px-3 py-2 text-sm ${mode === "publish" ? "bg-white/[0.08] text-white" : "text-zinc-500 hover:text-zinc-200"}`}>Publicar</button>
        </div>
        <div className="flex items-center gap-2"><span className="hidden items-center gap-1.5 text-[10px] text-zinc-600 lg:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />OmniRoute automático</span><button type="button" onClick={() => { if (confirmDiscard()) onClose(); }} className="rounded-lg border border-white/[0.08] px-3 py-2 text-xs text-zinc-300 hover:bg-white/[0.07] hover:text-white"><span className="hidden sm:inline">Voltar à conversa</span><span className="sm:hidden">Voltar</span></button><button type="button" onClick={() => { if (confirmDiscard()) onClose(); }} aria-label="Fechar ambiente do projeto" className="grid h-8 w-8 place-items-center rounded-full text-xl text-zinc-500 hover:bg-white/[0.07] hover:text-white">×</button></div>
      </header>
      <div className="grid min-h-0 flex-1 md:grid-cols-[280px_minmax(0,1fr)]">
      <StudioRail task={task} execution={execution} statusText={statusText} events={events} emAndamento={emAndamento} sending={sending} onTask={onTask} onStart={startMission} />
      <div className="min-h-0 min-w-0">
      {mode === "preview" ? <div className="flex h-full min-h-0 flex-col bg-[#111]">
        <div className="flex min-h-12 items-center justify-between gap-2 border-b border-white/[0.06] px-3 sm:px-4">
          <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-black/20 p-1" aria-label="Tamanho da visualização"><button type="button" onClick={() => setViewport("desktop")} className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${viewport === "desktop" ? "bg-white text-black" : "text-zinc-400 hover:bg-white/[0.08] hover:text-white"}`}>Desktop</button><button type="button" onClick={() => setViewport("mobile")} className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${viewport === "mobile" ? "bg-white text-black" : "text-zinc-400 hover:bg-white/[0.08] hover:text-white"}`}>Mobile</button></div>
          <div className="hidden min-w-0 max-w-xl flex-1 truncate rounded-md bg-black/30 px-3 py-1.5 text-center text-[11px] text-zinc-600 sm:block">{preview ? `${preview.kind === "runtime" ? "Executando" : "Estático"} · ${preview.entrypoint}` : "Aguardando uma página web"}</div>
          <div className="flex items-center gap-1"><button type="button" onClick={() => { setPicked(null); setInspectMode((value) => !value); }} disabled={!preview} className={`rounded-md px-2.5 py-1.5 text-xs ${inspectMode ? "bg-cyan-300 text-black" : "text-zinc-500 hover:bg-white/[0.06] hover:text-white"}`}>Selecionar elemento</button>{preview?.kind === "runtime" && <button type="button" onClick={() => setConsoleOpen((value) => !value)} className={`rounded-md px-2.5 py-1.5 text-xs ${consoleOpen ? "bg-white/[0.08] text-white" : "text-zinc-500 hover:bg-white/[0.06] hover:text-white"}`}>Console</button>}<button type="button" onClick={onReload} disabled={loading} className="rounded-md px-2.5 py-1.5 text-xs text-zinc-500 hover:bg-white/[0.06] hover:text-white disabled:opacity-40">Atualizar</button></div>
        </div>
        {picked && <div className="flex items-center justify-between gap-3 border-b border-cyan-300/15 bg-cyan-300/[0.055] px-4 py-2.5 text-xs"><span className="min-w-0 truncate text-cyan-100/80">Selecionado: <code>{picked.selector}</code>{picked.text ? ` · ${picked.text}` : ""}</span><button type="button" onClick={() => onElement(picked)} className="shrink-0 rounded-md bg-cyan-200 px-3 py-1.5 font-medium text-black">Pedir alteração</button></div>}
        <div className={`grid min-h-0 flex-1 ${consoleOpen && preview?.kind === "runtime" ? "grid-rows-[minmax(0,1fr)_180px]" : "grid-rows-1"}`}>
        <div className="flex min-h-0 items-start justify-center overflow-auto bg-[#0c0c0c] p-3 sm:p-5">
          {loading && <div className="m-auto flex items-center gap-2 text-sm text-zinc-500"><span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300" />Preparando preview seguro...</div>}
          {!loading && error && <div className="m-auto max-w-md text-center"><p className="text-sm text-zinc-300">{error}</p><p className="mt-2 text-xs leading-5 text-zinc-600">O projeto permanece intacto. Se for React ou Next.js, disponibilize primeiro as dependências do próprio projeto.</p></div>}
          {!loading && preview && <div className={`h-full overflow-hidden rounded-xl bg-white shadow-2xl transition-[width] ${viewport === "mobile" ? "w-[390px] max-w-full" : "w-full"}`}>{preview.kind === "runtime" ? <iframe ref={iframeRef} key={preview.preview_url} title="Preview executável do projeto" src={preview.preview_url} sandbox="allow-scripts allow-same-origin allow-forms" referrerPolicy="no-referrer" className="h-full min-h-[560px] w-full border-0 bg-white" /> : <iframe ref={iframeRef} key={preview.preview_url} title="Preview do projeto" src={preview.preview_url} sandbox="allow-scripts allow-same-origin" referrerPolicy="no-referrer" className="h-full min-h-[560px] w-full border-0 bg-white" />}</div>}
        </div>
        {consoleOpen && preview?.kind === "runtime" && <div className="min-h-0 overflow-auto border-t border-white/[0.07] bg-[#090909] p-3 font-mono text-[11px] leading-5 text-zinc-500" aria-label="Console do projeto">{runtimeLogs.length ? runtimeLogs.map((line) => <div key={line.seq}><span className="mr-2 text-zinc-700">{new Date(line.at * 1000).toLocaleTimeString("pt-BR")}</span>{line.message}</div>) : <p className="text-zinc-700">Aguardando mensagens do projeto...</p>}</div>}
        </div>
      </div> : mode === "files" ? <div className="grid h-full min-h-0 grid-cols-[150px_minmax(0,1fr)] bg-[#111] sm:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-r border-white/[0.07] bg-[#141414] p-2">
          <p className="px-2 pb-2 pt-1 text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-700">Arquivos editáveis</p>
          {files.length === 0 && !loading && <p className="px-2 py-6 text-xs leading-5 text-zinc-600">Nenhum arquivo textual disponível.</p>}
          {files.map((file) => <button key={file.path} type="button" onClick={() => { if (file.path === selectedFile?.path || confirmDiscard()) onOpenFile(file.path); }} className={`mb-0.5 block w-full truncate rounded-md px-2.5 py-2 text-left font-mono text-[11px] ${selectedFile?.path === file.path ? "bg-white/[0.08] text-zinc-100" : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-300"}`}>{file.path}</button>)}
        </aside>
        <section className="flex min-h-0 min-w-0 flex-col">
          <div className="flex min-h-12 items-center justify-between gap-3 border-b border-white/[0.06] px-4"><span className="truncate font-mono text-xs text-zinc-500">{selectedFile?.path ?? "Escolha um arquivo"}</span><button type="button" onClick={onSaveFile} disabled={loading || !selectedFile || fileDraft === selectedFile.content} className="rounded-md bg-white px-3 py-1.5 text-xs font-medium text-black disabled:bg-zinc-700 disabled:text-zinc-500">Salvar</button></div>
          {notice && <p className="border-b border-emerald-400/10 bg-emerald-400/[0.04] px-4 py-2 text-xs text-emerald-200/70">{notice}</p>}
          {error && <p className="border-b border-rose-400/10 bg-rose-400/[0.04] px-4 py-2 text-xs text-rose-200/70">{error}</p>}
          {selectedFile ? <textarea value={fileDraft} onChange={(event) => onDraft(event.target.value)} spellCheck={false} className="min-h-0 flex-1 resize-none bg-[#0c0c0c] p-5 font-mono text-[12px] leading-5 text-zinc-300 outline-none" aria-label={`Editor de ${selectedFile.path}`} /> : <div className="m-auto text-sm text-zinc-600">Escolha um arquivo para editar.</div>}
          <div className="border-t border-white/[0.06] px-4 py-2 text-[10px] text-zinc-700">Limite de 1 MB · salvamento protegido por versão e verificação de conflito</div>
        </section>
      </div> : mode === "versions" ? <div className="grid h-full min-h-0 md:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-h-0 overflow-y-auto p-4 sm:p-6">
          <div className="mb-5 flex items-center justify-between gap-3"><div><h2 className="text-lg font-medium text-zinc-100">Histórico protegido</h2><p className="mt-1 text-xs text-zinc-600">Cada entrega pode ser comparada e restaurada.</p></div><button type="button" onClick={onSaveVersion} disabled={loading} className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-black hover:bg-zinc-200 disabled:opacity-40">Salvar versão</button></div>
          {notice && <p className="mb-3 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.06] px-4 py-3 text-sm text-emerald-200/80">{notice}</p>}
          {error && <p className="mb-3 rounded-xl border border-rose-400/15 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-200/80">{error}</p>}
          {loading && versions.length === 0 && <p className="py-10 text-center text-sm text-zinc-600">Carregando versões...</p>}
          {!loading && versions.length === 0 && <p className="rounded-xl border border-dashed border-white/[0.08] py-12 text-center text-sm text-zinc-600">Nenhuma versão criada ainda.</p>}
          <div className="space-y-2">{versions.map((version) => <article key={version.version_id} className={`rounded-xl border p-4 ${selectedVersion === version.version_id ? "border-cyan-300/25 bg-cyan-300/[0.035]" : "border-white/[0.07] bg-white/[0.02]"}`}><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate text-sm font-medium text-zinc-200">{version.label}</h3><p className="mt-1 text-[11px] text-zinc-600">{reasonLabels[version.reason] ?? version.reason} · {new Date(version.created_at * 1000).toLocaleString("pt-BR")} · {version.file_count} arquivos · {formatarTamanho(version.size_bytes)}</p></div><div className="flex gap-2"><button type="button" onClick={() => onCompare(version.version_id)} disabled={loading} className="rounded-md px-2.5 py-1.5 text-xs text-zinc-400 hover:bg-white/[0.06] hover:text-white disabled:opacity-40">Comparar</button><button type="button" onClick={() => onRestore(version)} disabled={loading} className="rounded-md border border-white/[0.08] px-2.5 py-1.5 text-xs text-zinc-300 hover:bg-white/[0.06] disabled:opacity-40">Restaurar</button></div></div></article>)}</div>
        </div>
        <aside className="border-t border-white/[0.07] bg-[#141414] p-5 md:border-l md:border-t-0">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-700">Comparação com o projeto atual</p>
          {!comparison && <p className="mt-4 text-sm leading-6 text-zinc-600">Escolha uma versão para conferir o que mudaria antes de restaurar.</p>}
          {comparison && <div className="mt-5 space-y-3"><ChangeCount label="Serão adicionados" count={comparison.added.length} tone="emerald" /><ChangeCount label="Serão modificados" count={comparison.modified.length} tone="amber" /><ChangeCount label="Serão removidos" count={comparison.deleted.length} tone="rose" /><details className="pt-2 text-xs text-zinc-500"><summary className="cursor-pointer hover:text-zinc-300">Ver arquivos</summary><div className="mt-3 max-h-56 space-y-1 overflow-auto font-mono text-[10px] text-zinc-600">{[...comparison.added, ...comparison.modified, ...comparison.deleted].map((name) => <p key={name} className="truncate">{name}</p>)}</div></details></div>}
          <div className="mt-8 rounded-xl border border-white/[0.06] p-3 text-xs leading-5 text-zinc-600">Antes de restaurar, o Olympus cria um backup automático do estado atual.</div>
        </aside>
      </div> : <GitHubPanel projectId={projectId} busy={emAndamento} onDownload={onDownload} />}
      </div>
      </div>
    </section>
  </div>;
}

function GitHubPanel({ projectId, busy, onDownload }: { projectId: string; busy: boolean; onDownload: () => void }) {
  const [status, setStatus] = useState<CloudGitHubStatus | null>(null);
  const [commits, setCommits] = useState<CloudGitHubCommit[]>([]);
  const [publication, setPublication] = useState<CloudPublication | null>(null);
  const [token, setToken] = useState("");
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState(projectId.replace(/[^a-zA-Z0-9_.-]+/g, "-").slice(0, 100));
  const [branch, setBranch] = useState("main");
  const [newBranch, setNewBranch] = useState("");
  const [privateRepo, setPrivateRepo] = useState(false);
  const [linkMode, setLinkMode] = useState<"create" | "existing">("create");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const friendlyError = (value: unknown) => value instanceof ApiError ? value.message : "Não consegui concluir esta operação com o GitHub.";

  async function refresh() {
    setLoading(true); setError(null);
    try {
      const current = await api.obterGitHubProjeto(projectId);
      setStatus(current);
      if (current.connected && current.repository) {
        const [history, deployed] = await Promise.all([
          api.listarGitHubCommits(projectId).catch(() => [] as CloudGitHubCommit[]),
          current.repository.pages_url ? api.obterPublicacaoGitHub(projectId).catch(() => null) : Promise.resolve(null),
        ]);
        setCommits(history);
        setPublication(deployed);
      } else {
        setCommits([]); setPublication(null);
      }
    } catch (value) { setError(friendlyError(value)); }
    finally { setLoading(false); }
  }

  useEffect(() => { void refresh(); }, [projectId]);

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (!token.trim()) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      await api.conectarGitHub(token.trim());
      setToken(""); setNotice("Conta conectada somente para esta sessão.");
      await refresh();
    } catch (value) { setError(friendlyError(value)); setLoading(false); }
  }

  async function bind(event: FormEvent) {
    event.preventDefault();
    if (!repo.trim()) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      if (linkMode === "create") await api.criarGitHubRepositorio(projectId, repo.trim(), privateRepo);
      else await api.vincularGitHubRepositorio(projectId, owner.trim(), repo.trim(), branch.trim() || undefined);
      setNotice(linkMode === "create" ? "Repositório criado e conectado." : "Repositório conectado ao projeto.");
      await refresh();
    } catch (value) { setError(friendlyError(value)); setLoading(false); }
  }

  async function sync() {
    setLoading(true); setError(null); setNotice(null);
    try {
      const result = await api.sincronizarGitHub(projectId);
      setNotice(result.unchanged ? "O GitHub já possui a versão atual." : `${result.files_changed} arquivo(s) enviado(s) em um único commit seguro.`);
      await refresh();
    } catch (value) { setError(friendlyError(value)); setLoading(false); }
  }

  async function publish() {
    setLoading(true); setError(null); setNotice(null);
    try {
      const result = await api.publicarGitHubPages(projectId);
      setPublication(result); setNotice("Publicação iniciada. O endereço poderá levar alguns instantes para ficar disponível.");
      await refresh();
    } catch (value) { setError(friendlyError(value)); setLoading(false); }
  }

  async function createBranch(event: FormEvent) {
    event.preventDefault();
    if (!newBranch.trim()) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      await api.criarGitHubBranch(projectId, newBranch.trim());
      setNewBranch(""); setNotice("Nova branch criada e selecionada.");
      await refresh();
    } catch (value) { setError(friendlyError(value)); setLoading(false); }
  }

  async function disconnect() {
    setLoading(true); setError(null);
    try {
      await api.desconectarGitHub();
      setStatus((old) => old ? { ...old, connected: false, account: null } : old);
      setCommits([]); setPublication(null); setNotice("Conta desconectada. O repositório permaneceu intacto.");
    } catch (value) { setError(friendlyError(value)); }
    finally { setLoading(false); }
  }

  async function unlink() {
    if (!window.confirm("Desconectar este projeto do repositório? Nenhum arquivo será apagado no GitHub.")) return;
    setLoading(true); setError(null);
    try {
      await api.desvincularGitHubRepositorio(projectId);
      setStatus((old) => old ? { ...old, repository: null } : old);
      setCommits([]); setPublication(null); setNotice("Vínculo removido. O repositório remoto não foi alterado.");
    } catch (value) { setError(friendlyError(value)); }
    finally { setLoading(false); }
  }

  if (loading && !status) return <div className="flex h-full items-center justify-center text-sm text-zinc-600">Preparando publicação...</div>;

  return <div className="h-full overflow-y-auto bg-[#111] p-4 sm:p-7">
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-medium text-zinc-100">GitHub e publicação</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-500">Código versionado, commits automáticos e publicação estática sem expor credenciais.</p></div>{status?.connected && <button type="button" onClick={() => void disconnect()} className="rounded-lg px-3 py-2 text-xs text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-200">Desconectar conta</button>}</div>
      <section className="mt-7 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-cyan-300/15 bg-cyan-300/[0.045] p-5">
        <div><h3 className="text-sm font-medium text-zinc-100">Download local</h3><p className="mt-1 text-xs leading-5 text-zinc-500">Baixe uma cópia completa em ZIP. Não exige GitHub nem envia arquivos para serviços externos.</p></div>
        <button type="button" onClick={onDownload} disabled={busy} className="rounded-lg bg-white px-4 py-2.5 text-xs font-semibold text-black hover:bg-zinc-200 disabled:bg-zinc-700 disabled:text-zinc-500">Baixar ZIP</button>
      </section>
      {notice && <p className="mt-5 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.06] px-4 py-3 text-sm text-emerald-200/80">{notice}</p>}
      {error && <p className="mt-5 rounded-xl border border-rose-400/15 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-200/80">{error}</p>}

      {!status?.connected ? <form onSubmit={connect} className="mt-7 max-w-xl rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5">
        <h3 className="text-sm font-medium text-zinc-200">Conectar sua conta</h3>
        <p className="mt-2 text-xs leading-5 text-zinc-600">Use um token refinado com acesso apenas aos repositórios desejados. O Olympus o mantém somente na memória desta sessão.</p>
        <input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder="github_pat_..." className="mt-4 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 font-mono text-xs text-zinc-200 outline-none focus:border-white/[0.18]" />
        <button type="submit" disabled={loading || token.trim().length < 20} className="mt-3 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black disabled:bg-zinc-700 disabled:text-zinc-500">Conectar GitHub</button>
        <p className="mt-4 text-[10px] leading-4 text-zinc-700">Permissões mínimas: Contents leitura/escrita. Para publicar: Pages e Administration leitura/escrita.</p>
      </form> : !status.repository ? <form onSubmit={bind} className="mt-7 max-w-2xl rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5">
        <div className="flex items-center justify-between gap-3"><div><p className="text-xs text-zinc-600">Conectado como</p><p className="mt-0.5 text-sm font-medium text-zinc-200">@{status.account?.login}</p></div><div className="flex rounded-lg bg-black/25 p-1"><button type="button" onClick={() => setLinkMode("create")} className={`rounded-md px-3 py-1.5 text-xs ${linkMode === "create" ? "bg-white/[0.09] text-white" : "text-zinc-600"}`}>Criar novo</button><button type="button" onClick={() => setLinkMode("existing")} className={`rounded-md px-3 py-1.5 text-xs ${linkMode === "existing" ? "bg-white/[0.09] text-white" : "text-zinc-600"}`}>Usar existente</button></div></div>
        {linkMode === "existing" && <input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="Proprietário ou organização" className="mt-5 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-sm text-zinc-200 outline-none" />}
        <input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="Nome do repositório" className="mt-3 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-sm text-zinc-200 outline-none" />
        {linkMode === "existing" ? <input value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="Branch principal" className="mt-3 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-sm text-zinc-200 outline-none" /> : <label className="mt-4 flex items-center gap-2 text-xs text-zinc-500"><input type="checkbox" checked={privateRepo} onChange={(event) => setPrivateRepo(event.target.checked)} />Repositório privado — sincronização disponível, publicação gratuita desativada</label>}
        <button type="submit" disabled={loading || !repo.trim() || (linkMode === "existing" && !owner.trim())} className="mt-5 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black disabled:bg-zinc-700 disabled:text-zinc-500">{linkMode === "create" ? "Criar e conectar" : "Conectar repositório"}</button>
      </form> : <div className="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="space-y-5">
          <div className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-zinc-600">Repositório conectado</p><a href={status.repository.html_url} target="_blank" rel="noreferrer" className="mt-1 block text-base font-medium text-zinc-100 hover:text-cyan-200">{status.repository.owner}/{status.repository.repo}</a><p className="mt-1 font-mono text-[11px] text-zinc-600">branch: {status.repository.branch}</p></div><span className="rounded-full bg-emerald-400/[0.08] px-2.5 py-1 text-[10px] text-emerald-200/70">Commit automático ativo</span></div>
            <p className="mt-4 text-xs leading-5 text-zinc-600">Cada missão concluída gera um commit enquanto esta conta estiver conectada. Conflitos remotos são bloqueados; o Olympus nunca usa atualização forçada.</p>
            <div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={() => void sync()} disabled={loading || busy} className="rounded-lg border border-white/[0.09] px-3 py-2 text-xs text-zinc-300 hover:bg-white/[0.06] disabled:opacity-40">Sincronizar agora</button><button type="button" onClick={() => void publish()} disabled={loading || busy || status.repository.private} className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-black hover:bg-zinc-200 disabled:bg-zinc-700 disabled:text-zinc-500">Publicar em um clique</button><button type="button" onClick={() => void unlink()} disabled={loading || busy} className="rounded-lg px-3 py-2 text-xs text-zinc-600 hover:text-zinc-300 disabled:opacity-40">Remover vínculo</button></div>
            {status.repository.private && <p className="mt-3 text-[11px] text-amber-200/60">GitHub Pages gratuito nesta versão requer um repositório público.</p>}
          </div>
          {publication?.url && <div className="rounded-2xl border border-cyan-300/15 bg-cyan-300/[0.04] p-5"><p className="text-xs text-cyan-100/50">Aplicativo publicado · {publication.status}</p><a href={publication.url} target="_blank" rel="noreferrer" className="mt-2 block break-all text-sm text-cyan-100 hover:underline">{publication.url}</a></div>}
          <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5"><h3 className="text-sm font-medium text-zinc-200">Histórico remoto</h3><div className="mt-4 space-y-3">{commits.length ? commits.slice(0, 10).map((commit) => <a key={commit.sha} href={commit.html_url} target="_blank" rel="noreferrer" className="block rounded-xl border border-white/[0.05] p-3 hover:bg-white/[0.03]"><p className="truncate text-xs text-zinc-300">{commit.message.split("\n")[0]}</p><p className="mt-1 text-[10px] text-zinc-700">{commit.sha.slice(0, 7)} · {commit.author}{commit.date ? ` · ${new Date(commit.date).toLocaleString("pt-BR")}` : ""}</p></a>) : <p className="text-xs text-zinc-600">Nenhum commit carregado.</p>}</div></div>
        </section>
        <aside className="space-y-5">
          <form onSubmit={createBranch} className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5"><h3 className="text-sm font-medium text-zinc-200">Nova branch segura</h3><p className="mt-2 text-xs leading-5 text-zinc-600">Cria uma linha de trabalho a partir da versão remota atual.</p><input value={newBranch} onChange={(event) => setNewBranch(event.target.value)} placeholder="olympus/nova-versao" className="mt-4 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-3 py-2.5 font-mono text-xs text-zinc-200 outline-none" /><button type="submit" disabled={loading || busy || !newBranch.trim()} className="mt-3 w-full rounded-lg border border-white/[0.09] px-3 py-2 text-xs text-zinc-300 disabled:opacity-40">Criar branch</button></form>
          <div className="rounded-2xl border border-white/[0.06] p-4 text-[11px] leading-5 text-zinc-600">A publicação usa uma branch separada chamada <code className="text-zinc-400">olympus-pages</code>. O código-fonte e o histórico principal não são substituídos.</div>
        </aside>
      </div>}
      {status?.repository && <RailwayPanel projectId={projectId} busy={busy} repository={`${status.repository.owner}/${status.repository.repo}`} />}
    </div>
  </div>;
}

function RailwayPanel({ projectId, busy, repository }: { projectId: string; busy: boolean; repository: string }) {
  const [status, setStatus] = useState<CloudRailwayStatus | null>(null);
  const [secrets, setSecrets] = useState<CloudSecretReference[]>([]);
  const [token, setToken] = useState("");
  const [railwayProject, setRailwayProject] = useState("");
  const [service, setService] = useState("");
  const [environment, setEnvironment] = useState("");
  const [secretName, setSecretName] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const friendly = (value: unknown) => value instanceof ApiError ? value.message : "Não consegui concluir esta operação no Railway.";

  async function refresh() {
    setLoading(true); setError(null);
    try {
      const current = await api.obterRailwayProjeto(projectId);
      setStatus(current);
      setSecrets(current.binding ? await api.listarRailwaySegredos(projectId).catch(() => []) : []);
    } catch (value) { setError(friendly(value)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, [projectId]);

  async function connectRailway(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError(null);
    try { await api.conectarRailway(token.trim()); setToken(""); setNotice("Railway conectado somente para esta sessão."); await refresh(); }
    catch (value) { setError(friendly(value)); setLoading(false); }
  }
  async function bindRailway(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError(null);
    try { await api.vincularRailway(projectId, railwayProject.trim(), service.trim(), environment.trim(), repository); setNotice("Serviço Railway conectado ao mesmo repositório GitHub."); await refresh(); }
    catch (value) { setError(friendly(value)); setLoading(false); }
  }
  async function saveSecret(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError(null);
    try { await api.salvarRailwaySegredo(projectId, secretName.trim().toUpperCase(), secretValue); setSecretName(""); setSecretValue(""); setNotice("Segredo protegido atualizado; seu valor não será exibido."); await refresh(); }
    catch (value) { setError(friendly(value)); setLoading(false); }
  }
  async function deploy() {
    setLoading(true); setError(null); setNotice(null);
    try { const result = await api.publicarRailway(projectId, domain.trim() || undefined); setNotice(result.domain_status === "pending" ? "Publicação iniciada. Conclua os registros DNS indicados abaixo para ativar o domínio." : result.url ? `Publicação iniciada: ${result.url}` : "Publicação iniciada e aguardando o Railway."); await refresh(); }
    catch (value) { setError(friendly(value)); setLoading(false); }
  }
  async function rollback(target: CloudDeployment) {
    const current = status?.deployments[status.deployments.length - 1];
    if (!current || !window.confirm("Restaurar esta publicação? O projeto e o histórico do Olympus permanecerão intactos.")) return;
    setLoading(true); setError(null);
    try { await api.restaurarRailway(projectId, current.deployment_id, target.deployment_id); setNotice("Restauração segura iniciada."); await refresh(); }
    catch (value) { setError(friendly(value)); setLoading(false); }
  }

  return <section className="mt-7 border-t border-white/[0.07] pt-7">
    <div><h2 className="text-xl font-medium text-zinc-100">Aplicação completa</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-500">Publique backend, frontend e variáveis no Railway. O código continua sendo seu; o núcleo privado do Olympus não acompanha a entrega.</p></div>
    {notice && <p className="mt-5 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.06] px-4 py-3 text-sm text-emerald-200/80">{notice}</p>}
    {error && <p className="mt-5 rounded-xl border border-rose-400/15 bg-rose-400/[0.06] px-4 py-3 text-sm text-rose-200/80">{error}</p>}
    {!status?.connected ? <form onSubmit={connectRailway} className="mt-5 max-w-xl rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><h3 className="text-sm font-medium text-zinc-200">Conectar Railway</h3><p className="mt-2 text-xs leading-5 text-zinc-600">O token permanece apenas na memória desta sessão.</p><input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Token da conta Railway" className="mt-4 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 font-mono text-xs text-zinc-200 outline-none" /><button disabled={loading || token.trim().length < 20} className="mt-3 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black disabled:bg-zinc-700 disabled:text-zinc-500">Conectar Railway</button></form>
    : !status.binding ? <form onSubmit={bindRailway} className="mt-5 max-w-2xl rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><h3 className="text-sm font-medium text-zinc-200">Vincular serviço existente</h3><p className="mt-2 text-xs leading-5 text-zinc-600">No Railway, conecte previamente o repositório <span className="text-zinc-300">{repository}</span>. Informe os três identificadores exibidos pelo Railway.</p><input value={railwayProject} onChange={(event) => setRailwayProject(event.target.value)} placeholder="ID do projeto Railway" className="mt-4 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-xs text-zinc-200 outline-none" /><input value={service} onChange={(event) => setService(event.target.value)} placeholder="ID do serviço" className="mt-3 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-xs text-zinc-200 outline-none" /><input value={environment} onChange={(event) => setEnvironment(event.target.value)} placeholder="ID do ambiente" className="mt-3 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-xs text-zinc-200 outline-none" /><button disabled={loading || !railwayProject.trim() || !service.trim() || !environment.trim()} className="mt-4 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black disabled:bg-zinc-700 disabled:text-zinc-500">Vincular serviço</button></form>
    : <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]"><div className="space-y-5"><div className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-5"><div className="flex items-center justify-between gap-3"><div><p className="text-xs text-zinc-600">Serviço conectado</p><p className="mt-1 text-sm text-zinc-200">{status.binding.repository}</p></div><span className="rounded-full bg-emerald-400/[0.08] px-2.5 py-1 text-[10px] text-emerald-200/70">Revisão verificada</span></div><input value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="Domínio próprio (opcional)" className="mt-5 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-4 py-3 text-xs text-zinc-200 outline-none" /><button type="button" onClick={() => void deploy()} disabled={loading || busy} className="mt-3 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black disabled:bg-zinc-700 disabled:text-zinc-500">Publicar aplicação</button><p className="mt-3 text-[10px] leading-4 text-zinc-700">O Olympus sincroniza o GitHub, confere o commit executado pelo Railway e bloqueia divergências.</p></div><div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5"><h3 className="text-sm font-medium text-zinc-200">Publicações</h3><div className="mt-4 space-y-2">{status.deployments.length ? status.deployments.slice().reverse().map((item, index) => <div key={item.deployment_id} className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.05] p-3"><div className="min-w-0"><p className="truncate text-xs text-zinc-300">{item.url || item.deployment_id}</p><p className="mt-1 text-[10px] text-zinc-700">{item.status} · {item.provider_reference?.slice(0, 7)}</p></div>{index > 0 && <button type="button" onClick={() => void rollback(item)} disabled={loading || busy} className="text-[11px] text-zinc-500 hover:text-white">Restaurar</button>}</div>) : <p className="text-xs text-zinc-600">Nenhuma publicação nesta sessão.</p>}</div></div>{status.deployments.some((item) => item.dns_records?.length) && <div className="rounded-2xl border border-amber-300/15 bg-amber-300/[0.035] p-5"><h3 className="text-sm font-medium text-amber-100/80">Configuração DNS pendente</h3><div className="mt-3 space-y-2">{status.deployments.flatMap((item) => item.dns_records ?? []).map((record, index) => <div key={`${record.host}-${index}`} className="grid gap-1 rounded-lg bg-black/20 p-3 font-mono text-[10px] text-zinc-500 sm:grid-cols-[150px_minmax(0,1fr)]"><span>{record.host}</span><span className="break-all text-zinc-300">{record.value}</span></div>)}</div></div>}</div><form onSubmit={saveSecret} className="h-fit rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5"><h3 className="text-sm font-medium text-zinc-200">Variáveis protegidas</h3><p className="mt-2 text-xs leading-5 text-zinc-600">Os valores nunca são exibidos nem gravados no projeto.</p><input value={secretName} onChange={(event) => setSecretName(event.target.value.toUpperCase())} placeholder="NOME_DA_VARIAVEL" className="mt-4 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-3 py-2.5 font-mono text-xs text-zinc-200 outline-none" /><input type="password" autoComplete="off" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder="Valor secreto" className="mt-3 w-full rounded-xl border border-white/[0.09] bg-[#181818] px-3 py-2.5 font-mono text-xs text-zinc-200 outline-none" /><button disabled={loading || busy || secretName.trim().length < 2 || !secretValue} className="mt-3 w-full rounded-lg border border-white/[0.09] px-3 py-2 text-xs text-zinc-300 disabled:opacity-40">Salvar variável</button><div className="mt-4 space-y-1">{secrets.map((item) => <p key={item.name} className="rounded-md bg-black/20 px-2 py-1.5 font-mono text-[10px] text-zinc-600">{item.name} · v{item.version}</p>)}</div></form></div>}
  </section>;
}

function ChangeCount({ label, count, tone }: { label: string; count: number; tone: "emerald" | "amber" | "rose" }) {
  const colors = { emerald: "bg-emerald-400", amber: "bg-amber-300", rose: "bg-rose-400" };
  return <div className="flex items-center justify-between rounded-lg bg-white/[0.025] px-3 py-2.5"><span className="flex items-center gap-2 text-xs text-zinc-500"><span className={`h-1.5 w-1.5 rounded-full ${colors[tone]}`} />{label}</span><strong className="text-sm font-medium text-zinc-300">{count}</strong></div>;
}
