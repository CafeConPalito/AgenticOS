// components/agentic/app-header.tsx — cabecera translúcida con navegación superior (v7)
import * as React from "react";
import { ArrowLeft, ChevronRight, Moon, Search, SquareTerminal, Sun } from "lucide-react";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Kbd } from "./kbd"; // ../v1.1/code/components/agentic/kbd.tsx
import { cn } from "@/lib/utils";

export type TopSection = "tablero" | "ejecuciones" | "conocimiento" | "ajustes";
export interface Crumb { label: string; href?: string }
export interface TopNavItem { id: TopSection; label: string; count?: number }

const iconBtn = "grid size-8 shrink-0 place-items-center rounded-full text-foreground hover:bg-accent";

/**
 * v7:
 * - Va POR ENCIMA del contenido (absolute) con `glass`; el área de scroll lleva pt-14.
 * - Sin botón primario: «Nueva tarea» se abre con N, desde Ctrl+K o desde la tarjeta de agente.
 * - Conocimiento pasa a la navegación superior.
 */
export function AppHeader({ crumbs, nav, active, onBack, onOpenPalette, dockOpen, onToggleDock, connected, endpoint, theme, onToggleTheme }: {
  crumbs: Crumb[]; nav: TopNavItem[]; active?: TopSection; onBack?: () => void;
  onOpenPalette: () => void; dockOpen: boolean; onToggleDock: () => void;
  connected: boolean; endpoint: string; theme: "dark" | "light"; onToggleTheme: () => void;
}) {
  return (
    <header className="glass absolute inset-x-0 top-0 z-20 flex h-14 items-center gap-3 border-b border-sep px-[22px]">
      <a href="#/" aria-label="Agentic OS · Inicio" className="flex items-center gap-2.5 text-foreground hover:no-underline">
        <span className="relative grid size-7 place-items-center rounded-[10px] bg-[linear-gradient(145deg,#3B69E8,#1B3F8F)] shadow-[inset_0_0_0_1px_rgba(255,255,255,.14),0_6px_18px_-6px_#2E5BD6]">
          <span className="size-2.5 rounded-[3px] border-2 border-white" />
          <span className="absolute top-[5px] right-[5px] size-[5px] rounded-full bg-[#4CC9F0]" />
        </span>
        <span className="text-[15px] font-bold tracking-[-.01em] whitespace-nowrap">Agentic OS</span>
      </a>
      <span className="mx-1 h-[22px] w-px bg-border" />
      {onBack && (
        <button onClick={onBack} aria-label="Volver al inicio" className="grid size-7 place-items-center rounded-full bg-muted hover:bg-accent">
          <ArrowLeft className="size-[15px]" />
        </button>
      )}

      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap gap-1 text-[13px]">
          {crumbs.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && <BreadcrumbSeparator><ChevronRight className="size-[13px]" /></BreadcrumbSeparator>}
              <BreadcrumbItem className="min-w-0">
                {i === crumbs.length - 1
                  ? <BreadcrumbPage className="truncate px-1.5 font-medium">{c.label}</BreadcrumbPage>
                  : <BreadcrumbLink href={c.href} className="rounded-[5px] px-1.5 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground">{c.label}</BreadcrumbLink>}
              </BreadcrumbItem>
            </React.Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>

      <nav aria-label="Secciones" className="flex shrink-0 gap-0.5">
        {nav.map((n) => (
          <a key={n.id} href={`#/${n.id}`} aria-current={active === n.id ? "page" : undefined}
            className={cn("flex h-[30px] items-center gap-1.5 rounded-full px-2.5 text-[12.5px] whitespace-nowrap hover:bg-accent hover:text-foreground hover:no-underline",
              active === n.id ? "bg-accent text-foreground" : "text-muted-foreground")}>
            {n.label}
            {n.count != null && <span className="font-mono text-[11.5px] text-muted-foreground">{n.count}</span>}
          </a>
        ))}
      </nav>

      <button onClick={onOpenPalette} className="flex h-8 w-[220px] items-center gap-2 rounded-full bg-[color-mix(in_oklch,var(--muted)_80%,transparent)] pr-1.5 pl-3 text-[12.5px] text-muted-foreground">
        <Search className="size-3.5 shrink-0" />
        <span className="flex-1 truncate text-left">Buscar agentes, tareas o acciones…</span>
        <Kbd keys={["Ctrl", "K"]} />
      </button>
      <button onClick={onToggleDock} aria-label="Terminal (Ctrl+`)" aria-pressed={dockOpen} className={cn(iconBtn, dockOpen && "bg-accent")}>
        <SquareTerminal className="size-[15px]" />
      </button>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="flex items-center gap-1.5 text-xs whitespace-nowrap text-muted-foreground">
            <span className={cn("size-[7px] rounded-full", connected ? "bg-status-done" : "bg-status-failed")} />
            {connected ? "Conectado" : "Desconectado"}
          </span>
        </TooltipTrigger>
        <TooltipContent>Backend {connected ? "conectado" : "desconectado"} · <span className="font-mono">{endpoint}</span></TooltipContent>
      </Tooltip>
      <button onClick={onToggleTheme} aria-label="Cambiar tema" className={iconBtn}>
        {theme === "dark" ? <Sun className="size-[15px]" /> : <Moon className="size-[15px]" />}
      </button>
    </header>
  );
}

/** Uso:
 * <div className="relative flex h-screen flex-col overflow-hidden bg-background">
 *   <div aria-hidden className="bg-atmos pointer-events-none absolute inset-0" />
 *   <AppHeader … nav={[{id:"tablero",label:"Tablero",count:openTasks},{id:"ejecuciones",label:"Ejecuciones",count:liveSessions},{id:"conocimiento",label:"Conocimiento"},{id:"ajustes",label:"Ajustes"}]} />
 *   <main className="relative z-[1] min-h-0 flex-1 overflow-auto pt-14 [scroll-padding-top:56px]">…</main>
 *   {dockOpen && <TerminalDock … />}
 * </div>
 */
