// components/agentic/shell.tsx — AppSidebar, AppHeader, CommandPalette, OfflineBanner
import * as React from "react";
import {
  Bot, ChartColumn, FolderGit2, Inbox, LayoutDashboard, Moon, Plus, Search, Settings,
  SquareKanban, SquareTerminal, Sparkles, Sun, WifiOff,
} from "lucide-react";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuBadge,
  SidebarMenuButton, SidebarMenuItem, SidebarTrigger, useSidebar,
} from "@/components/ui/sidebar";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type Section = "dashboard" | "agents" | "projects" | "board" | "inbox" | "usage" | "settings";
export const NAV: { id: Section; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "agents", label: "Agentes", icon: Bot },
  { id: "projects", label: "Proyectos", icon: FolderGit2 },
  { id: "board", label: "Tablero", icon: SquareKanban },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "usage", label: "Consumo", icon: ChartColumn },
  { id: "settings", label: "Ajustes", icon: Settings },
];

function Logo() {
  return (
    <span className="relative grid size-7 shrink-0 place-items-center rounded-lg bg-[#2E5BD6]">
      <span className="size-2.5 rounded-[3px] border-2 border-white" />
      <span className="absolute top-[5px] right-[5px] size-[5px] rounded-full bg-[#4CC9F0]" />
    </span>
  );
}

/** Requiere <SidebarProvider style={{ "--sidebar-width": "232px", "--sidebar-width-icon": "60px" }}> */
export function AppSidebar({ active, onNavigate, inboxCount, connected, theme, onToggleTheme }: {
  active: Section; onNavigate: (s: Section) => void; inboxCount: number;
  connected: boolean; theme: "dark" | "light"; onToggleTheme: () => void;
}) {
  const { state } = useSidebar();
  return (
    <Sidebar collapsible="icon" className="border-sidebar-border">
      <SidebarHeader className="h-[52px] flex-row items-center gap-2.5 border-b border-sidebar-border px-3.5">
        <Logo />
        {state === "expanded" && <span className="flex-1 text-[15px] font-bold tracking-[-0.01em] whitespace-nowrap">Agentic OS</span>}
        <SidebarTrigger className="text-sidebar-muted hover:bg-sidebar-accent hover:text-white" aria-label="Colapsar barra lateral" />
      </SidebarHeader>
      <SidebarContent className="px-2.5 py-2.5">
        <SidebarMenu className="gap-0.5">
          {NAV.map(({ id, label, icon: Icon }) => (
            <SidebarMenuItem key={id}>
              <SidebarMenuButton
                isActive={active === id} tooltip={label} onClick={() => onNavigate(id)}
                className="h-[34px] gap-2.5 rounded-[7px] text-sidebar-muted hover:bg-sidebar-accent hover:text-white data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-white"
              >
                <Icon className="size-4" /><span>{label}</span>
              </SidebarMenuButton>
              {id === "inbox" && inboxCount > 0 && (
                <SidebarMenuBadge className="h-[18px] min-w-5 rounded-full bg-[#F5B547] px-1.5 text-[11px] font-bold text-[#0A1A33]">{inboxCount}</SidebarMenuBadge>
              )}
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarContent>
      <SidebarFooter className="gap-1.5 border-t border-sidebar-border p-2.5">
        <div className="flex h-8 items-center gap-[9px] px-2.5 text-xs whitespace-nowrap text-sidebar-muted" title={connected ? "Conectado" : "Desconectado"}>
          <span className={cn("size-2 shrink-0 rounded-full", connected ? "bg-status-done" : "bg-status-failed")} />
          {state === "expanded" && (connected ? "Conectado · v0.8.2" : "Desconectado · reintentando…")}
        </div>
        <SidebarMenuButton onClick={onToggleTheme} tooltip="Cambiar tema" className="h-8 gap-[9px] text-sidebar-muted hover:bg-sidebar-accent hover:text-white">
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          <span>{theme === "dark" ? "Tema claro" : "Tema oscuro"}</span>
        </SidebarMenuButton>
      </SidebarFooter>
    </Sidebar>
  );
}

export interface Crumb { label: string; onClick?: () => void }
export function AppHeader({ crumbs, onOpenPalette, dockOpen, onToggleDock, primary }: {
  crumbs: Crumb[]; onOpenPalette: () => void; dockOpen: boolean; onToggleDock: () => void;
  primary?: { label: string; onClick: () => void };
}) {
  return (
    <header className="flex h-[52px] shrink-0 items-center gap-3 border-b bg-background px-[18px]">
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap gap-1.5 text-[13px]">
          {crumbs.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && <BreadcrumbSeparator>/</BreadcrumbSeparator>}
              <BreadcrumbItem>
                {i === crumbs.length - 1 ? <BreadcrumbPage className="font-medium whitespace-nowrap">{c.label}</BreadcrumbPage>
                  : <BreadcrumbLink asChild><button onClick={c.onClick} className="rounded-[5px] px-1.5 py-0.5 whitespace-nowrap hover:bg-accent">{c.label}</button></BreadcrumbLink>}
              </BreadcrumbItem>
            </React.Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      <button onClick={onOpenPalette} className="flex h-8 w-[300px] items-center gap-2 rounded-lg border bg-subtle pr-2 pl-2.5 text-[12.5px] text-muted-foreground hover:border-ring">
        <Search className="size-3.5" /><span className="flex-1 text-left">Buscar o ejecutar un comando…</span>
        <kbd className="rounded border bg-card px-1.5 py-px font-mono text-[11px]">Ctrl K</kbd>
      </button>
      <Button variant="outline" onClick={onToggleDock} title="Terminal (Ctrl+`)" className={cn("h-8 gap-[7px]", dockOpen ? "bg-accent" : "bg-transparent")}>
        <SquareTerminal className="size-[15px]" />Terminal
      </Button>
      {primary && (
        <Button onClick={primary.onClick} className="h-8 gap-1.5 bg-primary-action font-medium text-white hover:bg-primary-action-hover">
          <Plus className="size-[15px]" />{primary.label}
        </Button>
      )}
    </header>
  );
}

export function OfflineBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="flex shrink-0 items-center gap-2.5 border-b border-[color-mix(in_oklch,var(--status-failed)_40%,transparent)] bg-[color-mix(in_oklch,var(--status-failed)_14%,var(--background))] px-[18px] py-[9px] text-[12.5px]">
      <WifiOff className="size-4 text-status-failed" />
      <strong className="font-medium">Backend desconectado.</strong>
      <span className="text-muted-foreground">No se pueden lanzar ni observar ejecuciones. Los agentes en curso siguen trabajando en sus terminales.</span>
      <Button size="sm" variant="outline" className="ml-auto h-[26px]" onClick={onRetry}>Reintentar ahora</Button>
      <span className="font-mono text-xs text-muted-foreground">ws://127.0.0.1:4317</span>
    </div>
  );
}

export function CommandPalette({ open, onOpenChange, onNavigate, onNewTask, onArchitect, onToggleDock, onToggleTheme, tasks, agents, onOpenTask, onOpenAgent }: {
  open: boolean; onOpenChange: (o: boolean) => void; onNavigate: (s: Section) => void;
  onNewTask: () => void; onArchitect: () => void; onToggleDock: () => void; onToggleTheme: () => void;
  tasks: { id: string; code: string; title: string; project: string }[]; agents: { id: string; label: string; cli: string }[];
  onOpenTask: (id: string) => void; onOpenAgent: (id: string) => void;
}) {
  React.useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); onOpenChange(!open); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [open, onOpenChange]);
  const run = (fn: () => void) => () => { onOpenChange(false); fn(); };
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} className="top-[12vh] w-[600px] translate-y-0 bg-popover">
      <CommandInput placeholder="Ir a, buscar tareas o ejecutar una acción…" />
      <CommandList className="max-h-[390px]">
        <CommandEmpty>Sin resultados</CommandEmpty>
        <CommandGroup heading="Ir a">
          {NAV.map(({ id, label, icon: I }) => <CommandItem key={id} onSelect={run(() => onNavigate(id))}><I />{label}</CommandItem>)}
        </CommandGroup>
        <CommandGroup heading="Acciones">
          <CommandItem onSelect={run(onNewTask)}><Plus />Nueva tarea<CommandShortcut>N</CommandShortcut></CommandItem>
          <CommandItem onSelect={run(onArchitect)}><Sparkles />Crear agente con el Arquitecto</CommandItem>
          <CommandItem onSelect={run(onToggleDock)}><SquareTerminal />Abrir / cerrar terminal<CommandShortcut>Ctrl `</CommandShortcut></CommandItem>
          <CommandItem onSelect={run(onToggleTheme)}><Sun />Cambiar tema claro / oscuro</CommandItem>
        </CommandGroup>
        <CommandGroup heading="Tareas">
          {tasks.map((t) => <CommandItem key={t.id} value={`${t.code} ${t.title}`} onSelect={run(() => onOpenTask(t.id))}><span className="font-mono text-muted-foreground">{t.code}</span>{t.title}<CommandShortcut>{t.project}</CommandShortcut></CommandItem>)}
        </CommandGroup>
        <CommandGroup heading="Agentes">
          {agents.map((a) => <CommandItem key={a.id} onSelect={run(() => onOpenAgent(a.id))}><Bot />{a.label}<CommandShortcut>{a.cli}</CommandShortcut></CommandItem>)}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
