// components/agentic/summary-aside.tsx — columna lateral agrupada de Inicio (v7)
// Sustituye a la «sidebar agrupada» de v1.1: la navegación está en AppHeader y esta columna agrupa
// lo secundario (proyectos, gasto, CLIs, conocimiento) SIN tarjetas, directamente sobre el fondo.
import * as React from "react";
import { ChevronDown, Plus } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { AgentAvatar } from "./primitives"; // ../code/components/agentic/primitives.tsx
import type { Agent, Project } from "@/lib/types";
import { cn } from "@/lib/utils";

export const WARN_AT = 80;   // ámbar
export const ALERT_AT = 95;  // genera petición en «Te necesitan» (ver dashboard.tsx)

export interface ProjectSummary { project: Project; open: number; activity: string; working: Agent[] }
export interface Quota { label: string; value: number; meta: string }
export interface CliAccount { id: string; email: string; plan: string; quotas: Quota[]; liveSessions: number; session?: "ok" | "down" }
export interface CliSummary { id: string; name: string; tag: string; accounts: CliAccount[] }

export const topQuota = (a: CliAccount): Quota => a.quotas.reduce((m, q) => (q.value > m.value ? q : m), a.quotas[0] ?? { label: "", value: 0, meta: "" });
const warnText = (v: number) => (v >= WARN_AT ? "text-status-waiting" : "text-muted-foreground");
const warnFill = (v: number) => (v >= WARN_AT ? "bg-status-waiting" : "bg-muted-foreground");
const row = "-mx-2 rounded-[9px] px-2 text-foreground hover:bg-subtle hover:no-underline";

export function SummaryAside({ projects, spend, limit, clis, knowledge, onNewProject, onAddCli }: {
  projects: ProjectSummary[]; spend: number; limit: number; clis: CliSummary[];
  knowledge: { sources: number; skills: number; newMemories: number };
  onNewProject: () => void; onAddCli: () => void;
}) {
  const nAcc = clis.reduce((m, c) => m + c.accounts.length, 0);
  const nSess = clis.reduce((m, c) => m + c.accounts.reduce((k, a) => k + a.liveSessions, 0), 0);
  const pct = Math.round((spend / limit) * 100);
  const eur = (v: number) => v.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

  return (
    <aside aria-label="Resumen" className="animate-rise-in sticky top-[84px] flex min-w-0 flex-col gap-[30px] border-l border-sep pt-5 pl-7 [animation-delay:.24s]">
      <AsideSection title="Proyectos" meta={`${projects.length} activos`} link={{ label: "Ver todos", href: "#/proyectos" }} onAdd={onNewProject} addLabel="Nuevo proyecto">
        {projects.map(({ project: p, open, activity, working }) => (
          <a key={p.id} href={`#/tablero/${p.id}`} title={activity} className={cn(row, "grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-px py-1.5")}>
            <span className="size-2 rounded-[2px]" style={{ background: p.color }} />
            <span className="truncate">{p.name}</span>
            <span className="text-xs whitespace-nowrap text-muted-foreground">{open} abiertas</span>
            <span className="col-start-2 truncate text-xs text-muted-foreground">{activity}</span>
            <span className="col-start-3 flex justify-end gap-0.5">{working.map((a) => <AgentAvatar key={a.id} agent={a} size={16} />)}</span>
          </a>
        ))}
        {!projects.length && <p className="text-xs text-muted-foreground">Aún no hay proyectos.</p>}
      </AsideSection>

      <section aria-labelledby="gs-h" className="flex flex-col gap-2.5">
        <div className="flex items-baseline gap-2">
          <h2 id="gs-h" className="eyebrow m-0 whitespace-nowrap">Gasto de hoy</h2>
          <span className="ml-auto font-mono"><strong className="text-xl font-bold tracking-[-.02em]">{eur(spend)}</strong><span className="text-muted-foreground"> / {limit} €</span></span>
        </div>
        <span className="relative h-1.5 rounded-full bg-muted">
          <span className={cn("absolute inset-y-0 left-0 rounded-full", warnFill(pct))} style={{ width: `${Math.min(pct, 100)}%` }} />
          <span title="Aviso al 80 %" className="absolute -inset-y-[3px] left-[80%] w-px bg-muted-foreground" />
        </span>
        <span className="text-xs text-muted-foreground">{pct}% del límite diario</span>
      </section>

      <AsideSection title="CLIs" meta={`${nAcc} cuentas · ${nSess} sesiones`} link={{ label: "Gestionar", href: "#/clis" }} onAdd={onAddCli} addLabel="Añadir CLI o cuenta">
        {clis.map((c) => <CliRow key={c.id} cli={c} />)}
      </AsideSection>

      <AsideSection title="Conocimiento y skills" link={{ label: "Abrir", href: "#/conocimiento" }}>
        <a href="#/conocimiento" className="text-xs text-pretty text-muted-foreground hover:text-foreground hover:no-underline">
          {knowledge.sources} fuentes · {knowledge.skills} skills activos · {knowledge.newMemories} memorias nuevas hoy
        </a>
      </AsideSection>
    </aside>
  );
}

function AsideSection({ title, meta, link, onAdd, addLabel, children }: {
  title: string; meta?: string; link?: { label: string; href: string }; onAdd?: () => void; addLabel?: string; children: React.ReactNode;
}) {
  const id = React.useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-1">
      <div className="mb-1.5 flex items-center gap-2">
        <h2 id={id} className="eyebrow m-0 shrink-0 whitespace-nowrap">{title}</h2>
        {meta && <span className="min-w-0 truncate text-xs text-muted-foreground">{meta}</span>}
        {link && <a href={link.href} className="ml-auto text-xs text-muted-foreground hover:text-foreground">{link.label}</a>}
        {onAdd && (
          <button onClick={onAdd} aria-label={addLabel} title={addLabel} className="grid size-6 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground">
            <Plus className="size-[13px]" />
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

function QuotaBar({ value, w = "w-14" }: { value: number; w?: string }) {
  return <span className={cn("h-1 overflow-hidden rounded-full bg-muted", w)}><span className={cn("block h-full", warnFill(value))} style={{ width: `${value}%` }} /></span>;
}

function CliRow({ cli }: { cli: CliSummary }) {
  const [open, setOpen] = React.useState(false);
  const top = Math.max(0, ...cli.accounts.flatMap((a) => a.quotas.map((q) => q.value)));
  const sess = cli.accounts.reduce((m, a) => m + a.liveSessions, 0);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger title={`Cuota más alta entre sus cuentas: ${top} %`}
        className={cn(row, "grid w-[calc(100%+16px)] grid-cols-[24px_minmax(0,1fr)_56px_34px_12px] items-center gap-x-2 gap-y-px py-1.5 text-left")}>
        <span className="grid h-[18px] place-items-center rounded-[5px] border font-mono text-[10px] font-bold text-muted-foreground">{cli.tag}</span>
        <span className="truncate">{cli.name}</span>
        <QuotaBar value={top} w="w-full" />
        <span className={cn("text-right font-mono text-xs", warnText(top))}>{top}%</span>
        <ChevronDown className={cn("size-3 text-muted-foreground transition-transform", open && "rotate-180")} />
        <span className="col-[2/6] truncate text-xs text-muted-foreground">
          {cli.accounts.length} {cli.accounts.length === 1 ? "cuenta" : "cuentas"} · {sess} {sess === 1 ? "sesión" : "sesiones"}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-0.5 pt-0.5 pb-1.5 pl-8">
        {cli.accounts.map((a) => {
          const q = topQuota(a);
          return (
            <a key={a.id} href="#/clis" title={`${q.label}: ${q.value} %`} className={cn(row, "grid grid-cols-[minmax(0,1fr)_56px_34px] items-center gap-x-2 gap-y-px py-[5px] text-[12.5px]")}>
              <span className="truncate">{a.email}</span>
              <QuotaBar value={q.value} w="w-full" />
              <span className={cn("text-right font-mono text-[11.5px]", warnText(q.value))}>{q.value}%</span>
              <span className="col-[1/4] text-[11.5px] whitespace-nowrap text-muted-foreground">
                {a.plan} · {a.liveSessions ? `${a.liveSessions} ${a.liveSessions === 1 ? "sesión" : "sesiones"}` : "libre"}
              </span>
            </a>
          );
        })}
      </CollapsibleContent>
    </Collapsible>
  );
}
