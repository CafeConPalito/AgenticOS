// components/agentic/command-palette.tsx — Ctrl+K, ayuda de atajos y atajos globales (v7)
import * as React from "react";
import {
  ArrowRight, Bot, CircleDot, Folder, FolderPlus, Keyboard, Plus, Search, SquareTerminal, SunMoon, Terminal, UsersRound,
} from "lucide-react";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "./kbd";
import type { Agent, Project, Task } from "@/lib/types";

type Icon = React.ComponentType<{ className?: string }>;
export interface PaletteItem { group: "Acciones" | "Ir a" | "Agentes" | "Proyectos" | "Tareas"; label: string; icon: Icon; keys?: string[]; run: () => void }

/** Construye los ítems en el orden de v7. Sin búsqueda se ocultan Proyectos y Tareas; con búsqueda, máximo 14. */
export function buildPaletteItems(o: {
  agents: Agent[]; projects: Project[]; tasks: Task[]; go: (hash: string) => void;
  newTask: () => void; newAgent: () => void; newTeam: () => void; newProject: () => void; addCli: () => void;
  openDock: () => void; toggleTheme: () => void; openHelp: () => void;
}): PaletteItem[] {
  return [
    { group: "Acciones", label: "Nueva tarea", icon: Plus, keys: ["N"], run: o.newTask },
    { group: "Acciones", label: "Nuevo agente", icon: Bot, run: o.newAgent },
    { group: "Acciones", label: "Nuevo equipo", icon: UsersRound, run: o.newTeam },
    { group: "Acciones", label: "Nuevo proyecto", icon: FolderPlus, run: o.newProject },
    { group: "Acciones", label: "Añadir CLI o cuenta", icon: SquareTerminal, run: o.addCli },
    { group: "Acciones", label: "Abrir terminal", icon: Terminal, run: o.openDock },
    { group: "Acciones", label: "Cambiar tema", icon: SunMoon, run: o.toggleTheme },
    { group: "Acciones", label: "Atajos de teclado", icon: Keyboard, keys: ["?"], run: o.openHelp },
    ...([["Inicio", ""], ["CLIs y cuentas", "clis"], ["Proyectos", "proyectos"], ["Conocimiento y skills", "conocimiento"], ["Tablero", "tablero"], ["Ejecuciones", "ejecuciones"], ["Ajustes", "ajustes"]] as const)
      .map(([label, h]) => ({ group: "Ir a" as const, label, icon: ArrowRight, run: () => o.go(`#/${h}`) })),
    ...o.agents.map((a) => ({ group: "Agentes" as const, label: `${a.name} · ${a.role}`, icon: Bot, run: () => o.go(`#/agente/${a.id}`) })),
    ...o.projects.map((p) => ({ group: "Proyectos" as const, label: p.name, icon: Folder, run: () => o.go(`#/tablero/${p.id}`) })),
    ...o.tasks.map((t) => ({ group: "Tareas" as const, label: `${t.code} · ${t.title}`, icon: CircleDot, run: () => o.go(`#/tarea/${t.id}`) })),
  ];
}

export function CommandPalette({ open, onOpenChange, items }: { open: boolean; onOpenChange: (o: boolean) => void; items: PaletteItem[] }) {
  const [q, setQ] = React.useState("");
  React.useEffect(() => { if (open) setQ(""); }, [open]);
  const qq = q.trim().toLowerCase();
  const shown = (qq ? items.filter((i) => i.label.toLowerCase().includes(qq)) : items.filter((i) => i.group !== "Tareas" && i.group !== "Proyectos")).slice(0, 14);
  const groups = [...new Set(shown.map((i) => i.group))];
  const run = (i: PaletteItem) => { onOpenChange(false); i.run(); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Overlay: bg-[rgba(3,10,22,.35)] backdrop-blur-[6px] animate-fade-in (en DialogOverlay) */}
      <DialogContent className="glass-pop animate-sheet-in top-[12vh] max-h-[470px] w-[600px] max-w-[calc(100vw-40px)] translate-y-0 gap-0 overflow-hidden rounded-[20px] border p-0 shadow-pop [animation-duration:.24s]">
        <DialogTitle className="sr-only">Paleta de comandos</DialogTitle>
        <Command shouldFilter={false} className="bg-transparent">
          <div className="flex h-[50px] items-center gap-2.5 border-b border-sep px-3.5 text-muted-foreground">
            <Search className="size-4 shrink-0" />
            <CommandInput value={q} onValueChange={setQ} placeholder="Busca agentes, tareas, proyectos o acciones…" className="h-full border-0 text-sm text-foreground" />
            <Kbd keys={["Esc"]} />
          </div>
          <CommandList className="max-h-none flex-1 overflow-auto p-1.5">
            <CommandEmpty className="px-2.5 py-[18px] text-muted-foreground">Sin resultados.</CommandEmpty>
            {groups.map((g) => (
              <CommandGroup key={g} heading={g} className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-muted-foreground">
                {shown.filter((i) => i.group === g).map((i) => (
                  <CommandItem key={g + i.label} value={g + i.label} onSelect={() => run(i)} className="h-9 gap-2.5 rounded-[10px] px-2.5 data-[selected=true]:bg-accent">
                    <i.icon className="size-[15px] text-muted-foreground" />
                    <span className="flex-1 truncate">{i.label}</span>
                    {i.keys && <Kbd keys={i.keys} />}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

export const SHORTCUTS: [group: string, rows: [label: string, keys: string[]][]][] = [
  ["General", [["Paleta de comandos", ["Ctrl", "K"]], ["Atajos de teclado", ["?"]], ["Abrir / cerrar la terminal", ["Ctrl", "`"]], ["Cerrar diálogo o panel", ["Esc"]]]],
  ["Crear", [["Nueva tarea", ["N"]]]],
];

export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-pop animate-sheet-in w-[520px] gap-0 rounded-[20px] p-0 shadow-pop">
        <DialogHeader className="border-b border-sep px-4 py-3.5"><DialogTitle className="text-[15px] font-medium">Atajos de teclado</DialogTitle><DialogDescription className="sr-only">Lista de atajos</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 px-4 pt-2 pb-4">
          {SHORTCUTS.map(([g, rows]) => (
            <div key={g} className="flex flex-col gap-0.5 pt-2">
              <div className="mb-1 text-[11.5px] text-muted-foreground">{g}</div>
              {rows.map(([l, k]) => <div key={l} className="flex h-7 items-center gap-2"><span className="flex-1">{l}</span><Kbd keys={k} /></div>)}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Atajos globales. Las teclas de un carácter respetan «Atajos de una tecla» y se ignoran al escribir o con un diálogo abierto. */
export function useGlobalShortcuts(h: {
  oneKey: boolean; blocked: boolean; togglePalette: () => void; toggleDock: () => void; closeAll: () => void; newTask: () => void; help: () => void;
}) {
  const ref = React.useRef(h); ref.current = h;
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const c = ref.current, tag = (e.target as HTMLElement)?.tagName?.toLowerCase(), typing = tag === "input" || tag === "textarea" || tag === "select", mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); c.togglePalette(); return; }
      if (mod && e.key === "`") { e.preventDefault(); c.toggleDock(); return; }
      if (e.key === "Escape") { c.closeAll(); return; }
      if (typing || !c.oneKey || c.blocked || mod || e.altKey) return;
      if (e.key.toLowerCase() === "n") { e.preventDefault(); c.newTask(); } else if (e.key === "?") c.help();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
