// app.tsx — layout de la aplicación (sidebar + header + contenido + dock)
import * as React from "react";
import { Toaster, toast } from "sonner";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AGENTS, INBOX, PROJECTS, TASKS, agentById } from "@/lib/mock-data";
import { AppHeader, AppSidebar, CommandPalette, OfflineBanner, type Crumb, type Section } from "@/components/agentic/shell";
import { TerminalDock } from "@/components/agentic/terminal";
import { DashboardScreen } from "@/screens/dashboard";
import { BoardScreen } from "@/screens/board";
import { TaskDetailScreen } from "@/screens/task-detail";
import { InboxScreen } from "@/screens/inbox";

type Route = { screen: Section } | { screen: "task"; taskId: string };

export default function App() {
  const [route, setRoute] = React.useState<Route>({ screen: "dashboard" });
  const [theme, setTheme] = React.useState<"dark" | "light">("dark");
  const [palette, setPalette] = React.useState(false);
  const [dock, setDock] = React.useState<{ open: boolean; pos: "bottom" | "right"; tab: string }>({ open: false, pos: "bottom", tab: "r1" });
  const connected = true; // ← estado real del WebSocket del backend

  React.useEffect(() => { document.documentElement.classList.toggle("dark", theme === "dark"); }, [theme]);
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.ctrlKey && e.key === "`") { e.preventDefault(); setDock((d) => ({ ...d, open: !d.open })); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);
  React.useEffect(() => {
    const t = setTimeout(() => toast.error("QA ha rechazado «Login con Google» → vuelve a Desarrollo", {
      description: "Quique · «redirige al panel tras el callback» falla", action: { label: "Ver tarea", onClick: () => openTask("t1") },
    }), 2200);
    return () => clearTimeout(t);
  }, []);

  const go = (s: Section) => setRoute({ screen: s });
  const openTask = (taskId: string) => setRoute({ screen: "task", taskId });
  const section: Section = route.screen === "task" ? "board" : route.screen;
  const newTask = () => {/* abrir <NewTaskDialog/> */};

  const crumbs: Crumb[] = route.screen === "task"
    ? (() => { const t = TASKS.find((x) => x.id === route.taskId)!; return [{ label: "Tablero", onClick: () => go("board") }, { label: PROJECTS.find((p) => p.id === t.projectId)!.name, onClick: () => go("projects") }, { label: `${t.code} · ${t.title}` }]; })()
    : [{ label: { dashboard: "Dashboard", agents: "Agentes", projects: "Proyectos", board: "Tablero", inbox: "Inbox", usage: "Consumo", settings: "Ajustes" }[route.screen] }];

  const primary = ["dashboard", "board", "task", "projects"].includes(route.screen) ? { label: route.screen === "projects" ? "Nuevo proyecto" : "Nueva tarea", onClick: newTask }
    : route.screen === "agents" ? { label: "Nuevo agente", onClick: () => {/* Arquitecto */} }
    : route.screen === "usage" ? { label: "Exportar CSV", onClick: () => toast.success("Exportado consumo_30d.csv") } : undefined;

  return (
    <TooltipProvider delayDuration={300}>
      <SidebarProvider style={{ "--sidebar-width": "232px", "--sidebar-width-icon": "60px" } as React.CSSProperties} className="h-screen min-w-[1200px]">
        <AppSidebar active={section} onNavigate={go} inboxCount={INBOX.filter((i) => i.status === "pending").length}
          connected={connected} theme={theme} onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")} />
        <SidebarInset className="flex min-w-0 flex-col bg-background">
          <AppHeader crumbs={crumbs} onOpenPalette={() => setPalette(true)} dockOpen={dock.open} onToggleDock={() => setDock({ ...dock, open: !dock.open })} primary={primary} />
          {!connected && <OfflineBanner onRetry={() => {}} />}
          <div className={dock.pos === "right" ? "flex min-h-0 flex-1 flex-row" : "flex min-h-0 flex-1 flex-col"}>
            <main className="min-h-0 min-w-0 flex-1 overflow-auto">
              {route.screen === "dashboard" && <DashboardScreen onOpenTask={openTask} onOpenAgent={() => go("agents")} onNewTask={newTask} onGoInbox={() => go("inbox")} onGoUsage={() => go("usage")} onArchitect={() => go("agents")} />}
              {route.screen === "board" && <BoardScreen onOpenTask={openTask} />}
              {route.screen === "task" && <TaskDetailScreen taskId={route.taskId} />}
              {route.screen === "inbox" && <InboxScreen onOpenTask={openTask} onOpenTerminal={(a) => setDock({ ...dock, open: true, tab: a === "quique" ? "r3" : a === "ana" ? "r2" : "r1" })} />}
              {/* agents, projects, usage, settings: ver screens.md y el prototipo HTML */}
            </main>
            {dock.open && (
              <TerminalDock position={dock.pos} active={dock.tab} onTab={(tab) => setDock({ ...dock, tab })}
                onSwap={() => setDock({ ...dock, pos: dock.pos === "right" ? "bottom" : "right" })}
                onExpand={() => openTask(dock.tab === "r2" ? "t2" : dock.tab === "r3" ? "t3" : "t1")} onClose={() => setDock({ ...dock, open: false })}
                tabs={[{ id: "r1", label: "Login con Google", agent: agentById("dev"), status: "running" }, { id: "r2", label: "Requisitos del checkout", agent: agentById("ana"), status: "running" }, { id: "r3", label: "QA carrito de compra", agent: agentById("quique"), status: "waiting" }]}>
                {/* <XtermView runId={dock.tab} readOnly /> */}
              </TerminalDock>
            )}
          </div>
        </SidebarInset>
      </SidebarProvider>
      <CommandPalette open={palette} onOpenChange={setPalette} onNavigate={go} onNewTask={newTask} onArchitect={() => go("agents")}
        onToggleDock={() => setDock({ ...dock, open: !dock.open })} onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
        tasks={TASKS.map((t) => ({ id: t.id, code: t.code, title: t.title, project: PROJECTS.find((p) => p.id === t.projectId)!.name }))}
        agents={AGENTS.filter((a) => !a.draft).map((a) => ({ id: a.id, label: `${a.name} · ${a.role}`, cli: a.cli }))}
        onOpenTask={openTask} onOpenAgent={() => go("agents")} />
      <Toaster position="bottom-right" theme={theme} duration={5200}
        toastOptions={{ classNames: { toast: "!bg-popover !border-border !text-foreground !rounded-[10px] !shadow-[0_12px_32px_rgba(0,0,0,.35)] font-sans", description: "!text-muted-foreground" } }} />
    </TooltipProvider>
  );
}
