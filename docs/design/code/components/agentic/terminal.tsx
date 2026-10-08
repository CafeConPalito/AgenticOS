// components/agentic/terminal.tsx — TerminalPanel (xterm.js), TerminalDock, RunTree
import * as React from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { Eye, Hand, Keyboard, Maximize2, PanelBottom, PanelRight, Undo2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { STATUS, fmtClock } from "@/lib/status";
import type { Agent, Run, Status } from "@/lib/types";
import { AgentAvatar, LiveDot } from "./primitives";

/** Tema xterm alineado con los tokens (la terminal es siempre oscura). */
export const XTERM_THEME = {
  background: "#050E1E", foreground: "#D7E1F0", cursor: "#4CC9F0", cursorAccent: "#050E1E",
  selectionBackground: "#2E5BD6", black: "#0A1A33", brightBlack: "#7F8DAA",
  red: "#FF6B6F", green: "#43D392", yellow: "#F5B547", blue: "#8FB4FF",
  magenta: "#B39CFF", cyan: "#4CC9F0", white: "#D7E1F0", brightWhite: "#FFFFFF",
};

/** Hook: monta xterm en un div y lo conecta a un PTY (p. ej. vía WebSocket del backend). */
export function useXterm(opts: { onData?: (d: string) => void; readOnly: boolean }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const term = React.useRef<Terminal>();
  React.useEffect(() => {
    const t = new Terminal({ fontFamily: "'Ubuntu Mono', monospace", fontSize: 13, lineHeight: 1.6, theme: XTERM_THEME, cursorBlink: true, convertEol: true });
    const fit = new FitAddon();
    t.loadAddon(fit); t.open(ref.current!); fit.fit();
    const ro = new ResizeObserver(() => fit.fit()); ro.observe(ref.current!);
    term.current = t;
    return () => { ro.disconnect(); t.dispose(); };
  }, []);
  React.useEffect(() => {
    const t = term.current; if (!t) return;
    t.options.disableStdin = opts.readOnly;
    const sub = t.onData((d) => !opts.readOnly && opts.onData?.(d));
    if (!opts.readOnly) t.focus();
    return () => sub.dispose();
  }, [opts.readOnly, opts.onData]);
  return { ref, term };
}

export function TerminalPanel({ title, intervening, onTakeControl, onGiveBack, onData, workingLabel, footer }: {
  title: string; intervening: boolean; onTakeControl: () => void; onGiveBack: () => void;
  onData?: (d: string) => void; workingLabel?: string; footer?: React.ReactNode;
}) {
  const { ref } = useXterm({ readOnly: !intervening, onData });
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2.5 p-3.5">
      <section
        aria-label="Terminal en vivo"
        className={cn("flex min-h-0 flex-1 flex-col overflow-hidden rounded-[11px] bg-terminal transition-[box-shadow,border-color] duration-200",
          intervening ? "border-2 border-status-intervening shadow-[0_0_0_4px_color-mix(in_oklch,var(--status-intervening)_22%,transparent)]" : "border")}
      >
        <header className="flex items-center gap-2.5 border-b border-terminal-border bg-terminal-header py-2 pr-2.5 pl-3 text-[#E6EDF7]">
          <span aria-hidden className="flex gap-[5px]">{[0, 1, 2].map((i) => <span key={i} className="size-[9px] rounded-full bg-[#1E3A66]" />)}</span>
          <span className="min-w-0 truncate font-mono text-[12.5px]">{title}</span>
          {intervening ? (
            <span className="inline-flex h-[22px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-status-intervening px-[9px] text-[11.5px] font-bold text-[#0A1A33]"><Keyboard className="size-3" />Estás interviniendo</span>
          ) : (
            <span className="inline-flex h-[22px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-[#13284D] px-[9px] text-[11.5px] text-[#C9D5EA]"><Eye className="size-3" />Solo lectura (observando)</span>
          )}
          <div className="ml-auto shrink-0">
            {intervening ? (
              <Button size="sm" variant="outline" onClick={onGiveBack} className="h-7 border-status-intervening bg-transparent text-status-intervening hover:bg-[#F5B547]/10 hover:text-status-intervening"><Undo2 />Devolver al agente</Button>
            ) : (
              <Button size="sm" onClick={onTakeControl} className="h-7 bg-[#2E5BD6] text-white hover:bg-[#3B69E8]"><Hand />Tomar control</Button>
            )}
          </div>
        </header>
        <div ref={ref} className="min-h-0 flex-1 px-3.5 py-3" />
        {!intervening && workingLabel && <div className="px-3.5 pb-2 font-mono text-[13px] text-[#7F8DAA]">{workingLabel}<span className="ml-0.5 inline-block h-[15px] w-2 animate-blink bg-[#4CC9F0] align-[-2px]" /></div>}
      </section>
      {footer && <div className="flex gap-4 font-mono text-[11.5px] text-muted-foreground">{footer}</div>}
    </div>
  );
}

/* ---------------- RunTree ---------------- */
export function RunTree({ root, selected, onSelect, now = 0 }: { root: Run; selected: string; onSelect: (id: string) => void; now?: number }) {
  return <div role="tree" aria-label="Árbol de ejecución" className="flex flex-col gap-0.5"><RunTreeNode run={root} depth={0} selected={selected} onSelect={onSelect} now={now} /></div>;
}
function RunTreeNode({ run, depth, selected, onSelect, now }: { run: Run; depth: number; selected: string; onSelect: (id: string) => void; now: number }) {
  const sel = selected === run.id;
  const secs = run.durationSec + (run.status === "running" ? now : 0);
  return (
    <>
      <button
        role="treeitem" aria-selected={sel} aria-level={depth + 1} onClick={() => onSelect(run.id)}
        className={cn("flex h-[34px] items-center gap-2 rounded-[7px] border pr-2 text-left hover:bg-accent", sel ? "border-ring bg-accent" : "border-transparent")}
        style={{ paddingLeft: 8 + depth * 16 }}
      >
        {depth > 0 && <span aria-hidden className="font-mono text-muted-foreground">└</span>}
        <LiveDot status={run.status} />
        <span className={cn("min-w-0 flex-1 truncate text-[12.5px]", depth > 0 && "font-mono")}>{run.name}</span>
        <span className="font-mono text-[11.5px] text-muted-foreground">{fmtClock(secs)}</span>
      </button>
      {run.children?.map((c) => <RunTreeNode key={c.id} run={c} depth={depth + 1} selected={selected} onSelect={onSelect} now={now} />)}
    </>
  );
}

/* ---------------- TerminalDock ---------------- */
export interface DockTab { id: string; label: string; agent: Agent; status: Status }
export function TerminalDock({ tabs, active, onTab, position, onSwap, onExpand, onClose, children }: {
  tabs: DockTab[]; active: string; onTab: (id: string) => void; position: "bottom" | "right";
  onSwap: () => void; onExpand: () => void; onClose: () => void; children: React.ReactNode;
}) {
  return (
    <aside aria-label="Terminal" className={cn("flex shrink-0 flex-col bg-terminal text-terminal-foreground", position === "bottom" ? "h-[260px] border-t" : "w-[440px] border-l")}>
      <div role="tablist" className="flex h-9 items-stretch border-b border-terminal-border bg-terminal-header">
        {tabs.map((t) => {
          const sel = t.id === active;
          return (
            <button key={t.id} role="tab" aria-selected={sel} onClick={() => onTab(t.id)}
              className={cn("flex items-center gap-[7px] whitespace-nowrap border-r border-terminal-border px-3 text-xs", sel ? "bg-terminal text-white shadow-[inset_0_2px_0_#4CC9F0]" : "text-[#9AA9C4] hover:text-white")}>
              <LiveDot status={t.status} className="size-[7px]" />
              <AgentAvatar agent={t.agent} size={16} withTooltip={false} />{t.label}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-0.5 px-1.5">
          {[
            { icon: position === "right" ? PanelBottom : PanelRight, label: position === "right" ? "Acoplar abajo" : "Acoplar a la derecha", on: onSwap },
            { icon: Maximize2, label: "Abrir detalle", on: onExpand },
            { icon: X, label: "Cerrar terminal", on: onClose },
          ].map(({ icon: I, label, on }) => (
            <button key={label} onClick={on} aria-label={label} title={label} className="grid size-7 place-items-center rounded-md text-[#9AA9C4] hover:bg-[#13284D] hover:text-white"><I className="size-[15px]" /></button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </aside>
  );
}
