"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError, type CloudProject } from "@/services/api";

type SidebarProps = { className?: string; onNavigate?: () => void; [key: string]: unknown };

function Icon({ children }: { children?: ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">{children}</svg>;
}

export function Brand({ className = "" }: { className?: string; [key: string]: unknown } = {}) {
  return <div className={`flex items-center gap-3 ${className}`}>
    <img src="/olympus-mark.png?v=2.6.2" alt="Olympus" className="olympus-logo h-11 w-11 shrink-0 object-contain" />
    <div>
      <div className="text-[15px] font-bold italic tracking-[0.18em]">OLYMPUS</div>
      <div className="mt-0.5 text-[10px] text-zinc-400">OLYMPUS 3.0.8</div>
    </div>
  </div>;
}

export function Sidebar({ className = "", onNavigate }: SidebarProps = {}) {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  const [projectsOpen, setProjectsOpen] = useState(pathname === "/missao");
  const [projects, setProjects] = useState<CloudProject[]>([]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [menuProject, setMenuProject] = useState<string | null>(null);
  const [projectAction, setProjectAction] = useState<string | null>(null);
  const [projectError, setProjectError] = useState("");
  const currentProject = search.get("project_id");

  async function loadProjects() {
    try {
      const items = await api.listarCloudProjetos();
      setProjects(items.slice().sort((a, b) => b.updated_at - a.updated_at));
      setProjectError("");
    } catch { /* A navegação principal continua disponível sem a lista. */ }
  }

  useEffect(() => { void loadProjects(); }, []);

  async function createProject() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setProjectError("");
    try {
      const project = await api.criarCloudProjeto({ name: name.trim() });
      setName(""); setCreating(false); setProjectsOpen(true);
      await loadProjects();
      router.push(`/missao?project_id=${encodeURIComponent(project.project_id)}`);
      onNavigate?.();
    } catch (error) {
      setProjectError(error instanceof ApiError ? error.message : "Não foi possível criar o projeto.");
    } finally { setBusy(false); }
  }

  async function renameProject(project: CloudProject) {
    const nextName = window.prompt("Novo nome do projeto:", project.name)?.trim();
    if (!nextName || nextName === project.name) { setMenuProject(null); return; }
    setProjectAction(project.project_id); setProjectError("");
    try {
      const updated = await api.renomearCloudProjeto(project.project_id, nextName);
      setProjects((items) => items.map((item) => item.project_id === project.project_id ? { ...item, ...updated } : item).sort((a, b) => b.updated_at - a.updated_at));
      setMenuProject(null);
    } catch (error) {
      setProjectError(error instanceof ApiError ? error.message : "Não foi possível renomear o projeto.");
    } finally { setProjectAction(null); }
  }

  async function deleteProject(project: CloudProject) {
    const confirmed = window.confirm(`Excluir o projeto “${project.name}”?\n\nO Olympus moverá o workspace para a lixeira interna de recuperação. Esta ação remove o projeto da lista.`);
    if (!confirmed) { setMenuProject(null); return; }
    setProjectAction(project.project_id); setProjectError("");
    try {
      await api.excluirCloudProjeto(project.project_id);
      setProjects((items) => items.filter((item) => item.project_id !== project.project_id));
      setMenuProject(null);
      if (currentProject === project.project_id) router.push("/missao");
    } catch (error) {
      setProjectError(error instanceof ApiError ? error.message : "Não foi possível excluir o projeto.");
    } finally { setProjectAction(null); }
  }

  function logout() {
    localStorage.removeItem("olympus_token");
    router.push("/login");
    onNavigate?.();
  }

  const nav = [
    { href: "/missao", label: "Nova missão", icon: <Icon><path d="M12 5v14M5 12h14" /></Icon> },
    { href: "/execucoes", label: "Histórico", icon: <Icon><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/><path d="M12 7v5l3 2"/></Icon> },
    { href: "/skills-fabric", label: "Skills Fabric", icon: <Icon><path d="m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3z" /></Icon> },
    { href: "/conexoes", label: "Inteligência", icon: <Icon><circle cx="8" cy="12" r="3"/><circle cx="17" cy="7" r="2"/><circle cx="17" cy="17" r="2"/><path d="m10.5 10.5 4.5-2.4m-4.5 5.4 4.5 2.4"/></Icon> },
  ];

  return <aside className={`flex h-full min-h-screen w-[250px] flex-col border-r border-black/[0.08] bg-white px-3 py-5 text-zinc-800 ${className}`}>
    <div className="px-4 pb-5"><Brand /></div>

    <nav className="space-y-1">
      <Link href="/missao" onClick={onNavigate} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${pathname === "/missao" && !currentProject ? "bg-zinc-100" : "hover:bg-zinc-50"}`}><Icon><path d="M12 5v14M5 12h14" /></Icon>Nova missão</Link>

      <div>
        <button type="button" onClick={() => setProjectsOpen((value) => !value)} className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm hover:bg-zinc-50"><span className="flex items-center gap-3"><Icon><path d="M3 7h7l2 2h9v10H3z"/></Icon>Projetos</span><span className="text-xs text-zinc-400">{projectsOpen ? "⌃" : "⌄"}</span></button>
        {projectsOpen && <div className="ml-3 border-l border-zinc-200 pl-2">
          <button type="button" onClick={() => setCreating((value) => !value)} className="my-1 w-full rounded-lg px-3 py-2 text-left text-xs text-zinc-500 hover:bg-zinc-50">+ Novo projeto</button>
          {creating && <div className="mb-2 px-2"><input aria-label="Nome do projeto" autoFocus value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void createProject(); }} placeholder="Nome do projeto" className="w-full rounded-lg border border-zinc-200 px-2.5 py-2 text-xs outline-none"/><button type="button" onClick={() => void createProject()} disabled={!name.trim() || busy} className="mt-1.5 w-full rounded-lg bg-zinc-900 px-2 py-2 text-xs text-white disabled:opacity-40">{busy ? "Criando…" : "Criar"}</button></div>}
          {projectError && <p role="alert" className="mx-2 mb-2 rounded-lg bg-rose-50 px-2.5 py-2 text-[11px] leading-4 text-rose-600">{projectError}</p>}
          <div className="max-h-[300px] space-y-0.5 overflow-y-auto">
            {projects.map((project) => <div key={project.project_id} className="relative group/project">
              <div className={`flex items-center rounded-lg ${currentProject === project.project_id ? "bg-zinc-100" : "hover:bg-zinc-50"}`}>
                <Link href={`/missao?project_id=${encodeURIComponent(project.project_id)}`} onClick={onNavigate} title={`Abrir e continuar ${project.name}`} className={`min-w-0 flex-1 truncate px-3 py-2 text-xs ${currentProject === project.project_id ? "font-medium text-zinc-900" : "text-zinc-500 hover:text-zinc-800"}`}>{project.name}</Link>
                <button type="button" aria-label={`Opções de ${project.name}`} onClick={() => setMenuProject((value) => value === project.project_id ? null : project.project_id)} disabled={projectAction === project.project_id} className="mr-1 rounded-md px-2 py-1 text-sm leading-none text-zinc-400 opacity-60 hover:bg-white hover:text-zinc-800 group-hover/project:opacity-100 disabled:opacity-30">•••</button>
              </div>
              {menuProject === project.project_id && <div className="absolute right-1 top-8 z-40 w-36 rounded-xl border border-zinc-200 bg-white p-1 shadow-lg">
                <Link href={`/missao?project_id=${encodeURIComponent(project.project_id)}`} onClick={() => { setMenuProject(null); onNavigate?.(); }} className="block rounded-lg px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50">Abrir / continuar</Link>
                <button type="button" onClick={() => void renameProject(project)} className="block w-full rounded-lg px-3 py-2 text-left text-xs text-zinc-700 hover:bg-zinc-50">Renomear</button>
                <button type="button" onClick={() => void deleteProject(project)} className="block w-full rounded-lg px-3 py-2 text-left text-xs text-rose-600 hover:bg-rose-50">Excluir</button>
              </div>}
            </div>)}
          </div>
          {!projects.length && !creating && <p className="px-3 py-2 text-[11px] text-zinc-400">Nenhum projeto ainda.</p>}
        </div>}
      </div>

      {nav.slice(1).map((item) => <Link key={item.href} href={item.href} onClick={onNavigate} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ${pathname === item.href ? "bg-zinc-100" : "hover:bg-zinc-50"}`}>{item.icon}{item.label}</Link>)}
    </nav>

    <div className="mt-auto border-t border-zinc-200 pt-4">
      <Link href="/configuracoes" onClick={onNavigate} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50"><Icon><circle cx="12" cy="8" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/></Icon>Organização</Link>
      <Link href="/logs" onClick={onNavigate} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50"><Icon><path d="M5 6h14M5 12h10M5 18h7"/></Icon>Detalhes técnicos</Link>
      <button type="button" onClick={logout} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50"><Icon><path d="M10 17l5-5-5-5M15 12H3M21 3v18"/></Icon>Sair</button>
    </div>
  </aside>;
}

export function MobileNav() {
  const [open, setOpen] = useState(false);
  return <div className="md:hidden">
    <div className="sticky top-0 z-30 flex h-14 items-center border-b border-black/[0.08] bg-white px-4">
      <button type="button" aria-label="Abrir navegação" onClick={() => setOpen(true)} className="rounded-lg p-2 text-zinc-600 hover:bg-zinc-100">
        <Icon><path d="M4 7h16M4 12h16M4 17h16" /></Icon>
      </button>
      <span className="ml-3 text-sm font-bold italic tracking-[0.16em] text-zinc-800">OLYMPUS</span>
      <span className="ml-2 text-[10px] text-zinc-400">3.0.8</span>
    </div>
    {open && <div className="fixed inset-0 z-50 flex">
      <button type="button" aria-label="Fechar navegação" onClick={() => setOpen(false)} className="absolute inset-0 bg-black/30" />
      <div className="relative z-10 h-full bg-white shadow-xl">
        <Sidebar onNavigate={() => setOpen(false)} />
      </div>
    </div>}
  </div>;
}

export default Sidebar;
