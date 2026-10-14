// screens/dashboard.tsx — Inicio v7: «Te necesitan» + agentes por equipo | columna de resumen
import * as React from "react";
import { CircleCheck, Gauge, Hand, Pencil, Plus, UsersRound } from "lucide-react";
import { toast } from "sonner";
import { AgentAvatar } from "@/components/agentic/primitives";
import { RequestActions, REQUEST_ORDER, type Request, type RequestHandlers } from "@/components/agentic/request-actions"; // v1.1
import { SummaryAside, topQuota, ALERT_AT, type CliSummary, type ProjectSummary } from "@/components/agentic/summary-aside";
import type { Agent, Project } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ---------- Tipos de vista ---------- */
export interface LiveSession { id: string; taskId: string; code: string; title: string; project: Project; state: "running" | "starting" | "waiting" | "interrupted"; elapsed: string }
export interface AgentVM { agent: Agent; status: "running" | "waiting" | "interrupted" | "idle" | "draft"; statusLabel: string; cliTag: string; sessions: LiveSession[]; queued: number; cost: string; tokens: string; pctOfLimit: number; pending: number }
export interface Team { id: string; name: string; description: string; agents: AgentVM[] }
export interface CliAlert { accountId: string; title: string; context: string; cta: string }

const STATUS_COLOR: Record<AgentVM["status"], string> = { running: "text-status-running", waiting: "text-status-waiting", interrupted: "text-status-failed", idle: "text-status-done", draft: "text-status-review" };
const SESSION_DOT: Record<LiveSession["state"], string> = { running: "bg-status-running animate-live-pulse", starting: "bg-status-queued", waiting: "bg-status-waiting", interrupted: "bg-status-failed" };
const avatarGloss = "[background-image:linear-gradient(150deg,rgba(255,255,255,.34),transparent_58%)] shadow-[inset_0_0_0_1px_rgba(255,255,255,.2)]";

/** Regla v7: una petición de sistema por cuenta con cuota ≥ 95 % o sesión caída, salvo las pospuestas. */
export function cliAlerts(clis: CliSummary[], snoozed: string[]): CliAlert[] {
  return clis.flatMap((c) => c.accounts.filter((a) => !snoozed.includes(a.id)).flatMap((a) => {
    const q = topQuota(a), down = a.session === "down";
    if (!down && q.value < ALERT_AT) return [];
    return [{
      accountId: a.id,
      title: down ? `${c.name}: sesión caída en ${a.email}` : `${c.name} casi sin cuota · ${q.value} %`,
      context: down ? "Los agentes que usan esta cuenta están en pausa hasta que vuelvas a iniciar sesión." : `${a.email} · ${q.label}: ${q.meta}. Cambia sus agentes a otra cuenta o espera al reinicio.`,
      cta: down ? "Reconectar" : "Revisar cuentas",
    }];
  }));
}

export function DashboardScreen(p: {
  userName: string; dateLabel: string; liveSessions: number; working: number; spendLabel: string;
  requests: (Request & { agent: Agent; taskLabel: string; taskHref: string })[]; handlers: RequestHandlers;
  teams: Team[]; projects: ProjectSummary[]; spend: number; limit: number; clis: CliSummary[];
  knowledge: { sources: number; skills: number; newMemories: number };
  onOpenAgent: (id: string) => void; onAssign: (agentId: string) => void; onUsage: (agentId: string) => void;
  onNewTeam: () => void; onNewAgent: (teamId: string) => void; onEditTeam: (teamId: string) => void;
  onNewProject: () => void; onAddCli: () => void; onManageClis: () => void;
}) {
  const [showAll, setShowAll] = React.useState(false);
  const [snoozed, setSnoozed] = React.useState<string[]>([]);
  const [hoverAgent, setHoverAgent] = React.useState<string | null>(null);
  const sorted = [...p.requests].sort((a, b) => REQUEST_ORDER[a.type] - REQUEST_ORDER[b.type]);
  const shown = showAll ? sorted : sorted.slice(0, 3);
  const alerts = cliAlerts(p.clis, snoozed);
  const total = sorted.length + alerts.length;

  return (
    <div data-screen-label="Inicio" className="mx-auto grid max-w-[1520px] grid-cols-[minmax(0,1fr)_300px] items-start gap-12 px-8 pt-7 pb-14">
      <div className="flex min-w-0 flex-col gap-8">
        {/* Saludo */}
        <div className="animate-rise-in flex min-w-0 flex-col gap-3.5">
          <div className="font-mono text-[11.5px] tracking-[.14em] text-muted-foreground uppercase">{p.dateLabel} · {p.liveSessions} sesiones en vivo</div>
          <h1 className="-mt-1.5 text-[40px] leading-[1.05] font-bold tracking-[-.035em] whitespace-nowrap">Buenos días, {p.userName}</h1>
          <div className="flex flex-wrap items-center gap-2 text-[13px] whitespace-nowrap text-muted-foreground">
            <Chip><span className="size-[7px] rounded-full bg-status-running animate-live-pulse" /><b className="font-medium text-foreground">{p.working}</b>trabajando</Chip>
            <Chip><span className="size-[7px] rounded-full bg-status-waiting" /><b className="font-medium text-foreground">{total}</b>esperan respuesta</Chip>
            <Chip><b className="font-mono font-medium text-foreground">{p.spendLabel}</b>gastados hoy</Chip>
          </div>
        </div>

        {/* Te necesitan */}
        {total > 0 ? (
          <section aria-labelledby="rq-h" className="animate-rise-in overflow-hidden rounded-[20px] border border-[color-mix(in_oklch,var(--status-waiting)_50%,var(--sep))] bg-[linear-gradient(180deg,color-mix(in_oklch,var(--status-waiting)_10%,var(--card))_0,var(--card)_150px)] shadow-[0_0_0_4px_color-mix(in_oklch,var(--status-waiting)_7%,transparent),0_22px_50px_-18px_color-mix(in_oklch,var(--status-waiting)_30%,transparent),var(--shadow-card)] [animation-delay:.08s]">
            <div className="flex h-[60px] items-center gap-3 pr-3.5 pl-[18px]">
              <span className="grid size-[30px] place-items-center rounded-full bg-[#F5B547] text-[#0A1A33] shadow-[0_0_22px_color-mix(in_oklch,#F5B547_50%,transparent)]"><Hand className="size-[15px]" /></span>
              <h2 id="rq-h" className="text-lg font-bold tracking-[-.02em]">Te necesitan</h2>
              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-[#F5B547] px-[7px] text-[11.5px] font-bold text-[#0A1A33]">{total}</span>
              {sorted.length > 3 && (
                <button onClick={() => setShowAll((v) => !v)} aria-expanded={showAll} className="ml-auto h-[30px] rounded-full px-3 text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground">
                  {showAll ? "Ver menos" : `Ver todas · ${sorted.length}`}
                </button>
              )}
            </div>
            {shown.map((r) => (
              <article key={r.id} onMouseEnter={() => setHoverAgent(r.agentId)} onMouseLeave={() => setHoverAgent(null)} className="grid grid-cols-[30px_minmax(0,1fr)] gap-3.5 border-t border-sep px-[18px] py-4">
                <AgentAvatar agent={r.agent} size={30} className={avatarGloss} />
                <div className="flex min-w-0 flex-col gap-1.5">
                  <div className="flex items-baseline gap-3"><span className="min-w-0 flex-1 text-sm font-medium text-pretty">{r.title}</span><span className="shrink-0 text-xs text-muted-foreground">{r.when}</span></div>
                  <div className="flex min-w-0 items-center gap-1.5 text-xs whitespace-nowrap text-muted-foreground">
                    <TypeLabel type={r.type} /><span>·</span><a href={`#/agente/${r.agentId}`} className="text-muted-foreground hover:text-foreground">{r.agent.name}</a><span>·</span>
                    <a href={r.taskHref} className="truncate text-muted-foreground hover:text-foreground">{r.taskLabel}</a>
                  </div>
                  {r.command && <code className="self-start rounded-lg bg-terminal px-2 py-[3px] font-mono text-xs text-[#E6EDF7]">{r.command}</code>}
                  {r.context && <p className="text-[12.5px] text-pretty text-muted-foreground">{r.context}</p>}
                  <div className="mt-1"><RequestActions req={r} {...p.handlers} /></div>
                </div>
              </article>
            ))}
            {alerts.map((a) => (
              <CliAlertItem key={a.accountId} alert={a} onManage={p.onManageClis}
                onSnooze={() => { setSnoozed((s) => [...s, a.accountId]); toast.success("Aviso pospuesto"); }} />
            ))}
          </section>
        ) : (
          <div className="flex items-center gap-2 text-muted-foreground"><CircleCheck className="size-[15px] text-status-done" />Nada pendiente. Tus agentes no necesitan nada de ti ahora mismo.</div>
        )}

        {/* Agentes por equipo */}
        <section aria-labelledby="eq-h" className="animate-rise-in flex min-w-0 flex-col gap-[26px] [animation-delay:.16s]">
          <div className="flex items-center gap-2.5">
            <h2 id="eq-h" className="text-lg font-bold tracking-[-.02em]">Agentes</h2>
            <span className="text-xs text-muted-foreground">{p.teams.length} equipos · {p.teams.reduce((m, t) => m + t.agents.length, 0)} agentes</span>
            <button onClick={p.onNewTeam} className="ml-auto flex h-[30px] items-center gap-1.5 rounded-full px-3 text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground"><UsersRound className="size-3.5" />Nuevo equipo</button>
          </div>
          {p.teams.map((t) => {
            const active = t.agents.filter((a) => a.status === "running" || a.status === "waiting").length;
            return (
              <div key={t.id} className="flex min-w-0 flex-col gap-2.5">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="font-bold tracking-[-.005em] whitespace-nowrap">{t.name}</span>
                  <span title={t.description} className="truncate text-xs text-muted-foreground">{t.agents.length} {t.agents.length === 1 ? "agente" : "agentes"} · {active} activos</span>
                  <span className="h-px min-w-6 flex-1 bg-[linear-gradient(90deg,var(--sep),transparent)]" />
                  <button onClick={() => p.onNewAgent(t.id)} className="flex h-[26px] items-center gap-[5px] rounded-full px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"><Plus className="size-[13px]" />Agente</button>
                  <button onClick={() => p.onEditTeam(t.id)} aria-label={`Editar ${t.name}`} className="grid size-[26px] place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"><Pencil className="size-3" /></button>
                </div>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3">
                  {t.agents.map((vm) => (
                    <AgentCard key={vm.agent.id} vm={vm} highlighted={hoverAgent === vm.agent.id}
                      onOpen={() => p.onOpenAgent(vm.agent.id)} onAssign={() => p.onAssign(vm.agent.id)} onUsage={() => p.onUsage(vm.agent.id)} />
                  ))}
                  {!t.agents.length && (
                    <button onClick={() => p.onNewAgent(t.id)} className="h-24 rounded-[14px] border border-dashed border-input text-muted-foreground hover:border-ring hover:text-foreground">Sin agentes · Añadir el primero</button>
                  )}
                </div>
              </div>
            );
          })}
        </section>
      </div>

      <SummaryAside projects={p.projects} spend={p.spend} limit={p.limit} clis={p.clis} knowledge={p.knowledge} onNewProject={p.onNewProject} onAddCli={p.onAddCli} />
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="flex h-[30px] items-center gap-[7px] rounded-full border border-sep bg-[color-mix(in_oklch,var(--card)_65%,transparent)] px-[13px] backdrop-blur-[10px]">{children}</span>;
}

const TYPE_LABEL: Record<Request["type"], string> = { approval: "Aprobación", question: "Pregunta", blocked: "Bloqueo", interrupted: "Interrumpida", done: "Completada" };
function TypeLabel({ type }: { type: Request["type"] }) {
  // v7: el tipo NO se colorea (el ámbar del panel es el único color fuerte).
  return <span className="flex items-center gap-[5px]">{TYPE_LABEL[type]}</span>;
}

/* ---------- Aviso de CLI ---------- */
export function CliAlertItem({ alert, onManage, onSnooze }: { alert: CliAlert; onManage: () => void; onSnooze: () => void }) {
  return (
    <article className="grid grid-cols-[30px_minmax(0,1fr)] gap-3.5 border-t border-sep px-[18px] py-4">
      <span className="grid size-[30px] place-items-center rounded-[9px] bg-muted text-status-waiting"><Gauge className="size-[15px]" /></span>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex items-baseline gap-3"><span className="min-w-0 flex-1 text-sm font-medium">{alert.title}</span><span className="shrink-0 text-xs text-muted-foreground">ahora</span></div>
        <div className="text-xs text-muted-foreground">Aviso del sistema · CLIs y cuentas</div>
        <p className="text-[12.5px] text-pretty text-muted-foreground">{alert.context}</p>
        <div className="mt-1 flex gap-1.5">
          <button onClick={onManage} className="h-7 rounded-full bg-primary-action px-3 font-medium text-white hover:bg-primary-action-hover">{alert.cta}</button>
          <button onClick={onSnooze} className="h-7 rounded-full border px-3 hover:bg-accent">Posponer</button>
        </div>
      </div>
    </article>
  );
}

/* ---------- AgentCard v7 ---------- */
export function AgentCard({ vm, highlighted, onOpen, onAssign, onUsage }: { vm: AgentVM; highlighted: boolean; onOpen: () => void; onAssign: () => void; onUsage: () => void }) {
  const { agent: a } = vm;
  return (
    <div role="link" tabIndex={0} aria-label={`${a.name}, ${a.role}. ${vm.statusLabel}`} onClick={onOpen} onKeyDown={(e) => e.key === "Enter" && onOpen()}
      className={cn("group bg-card-grad relative flex cursor-pointer flex-col gap-2 rounded-2xl border px-3.5 pt-[13px] pb-2.5 shadow-card hover:-translate-y-px hover:border-ring",
        highlighted ? "border-status-waiting shadow-[0_0_0_3px_color-mix(in_oklch,var(--status-waiting)_30%,transparent),var(--shadow-card)]"
          : vm.pending ? "border-[color-mix(in_oklch,var(--status-waiting)_55%,var(--border))]" : "border-sep")}>
      {vm.status === "running" && (
        <span aria-hidden className="animate-sweep absolute inset-x-4 -top-px h-0.5 rounded-sm bg-[linear-gradient(90deg,transparent_0,var(--status-running)_50%,transparent_100%)] bg-[length:50%_100%] bg-no-repeat" />
      )}
      {vm.pending > 0 && (
        <span className="absolute -top-[9px] right-3 flex h-[18px] items-center rounded-full bg-[#F5B547] px-2 text-[10.5px] font-bold text-[#0A1A33] shadow-[0_0_0_3px_var(--background)]">
          {vm.pending === 1 ? "1 petición" : `${vm.pending} peticiones`}
        </span>
      )}

      <div className="flex min-w-0 items-center gap-2.5">
        <AgentAvatar agent={a} size={30} className={cn(avatarGloss, "rounded-[9px]")} />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{a.name}</span>
        <span className={cn("flex shrink-0 items-center gap-[5px] text-xs font-medium whitespace-nowrap", STATUS_COLOR[vm.status])}>
          <span className={cn("size-1.5 rounded-full bg-current", vm.status === "running" && "animate-live-pulse")} />{vm.statusLabel}
        </span>
      </div>

      <div className="flex min-h-6 min-w-0 flex-col gap-0.5">
        {vm.sessions.map((s) => (
          <a key={s.id} href={`#/tarea/${s.taskId}`} onClick={(e) => e.stopPropagation()} title={`${s.title} · ${s.project.name} · sesión ${s.id}`}
            className="-mx-1.5 flex h-6 min-w-0 items-center gap-2 rounded-[7px] px-1.5 whitespace-nowrap text-foreground hover:bg-subtle hover:no-underline">
            <span className={cn("size-1.5 shrink-0 rounded-full", SESSION_DOT[s.state])} />
            <span className="shrink-0 font-mono text-xs text-muted-foreground">{s.code}</span>
            <span className="min-w-0 flex-1 truncate">{s.title}</span>
            <span className="size-[7px] shrink-0 rounded-[2px]" style={{ background: s.project.color }} />
            <span className="shrink-0 font-mono text-xs text-muted-foreground">{s.elapsed}</span>
          </a>
        ))}
        {!vm.sessions.length && (
          <div className="flex h-6 items-center truncate text-muted-foreground">{vm.status === "draft" ? "Borrador · actívalo desde su ficha" : "Disponible · sin tareas en curso"}</div>
        )}
      </div>

      {/* Secundario ↔ consumo: misma celda; el hover/foco intercambia opacidades */}
      <div className="grid items-center">
        <div className="col-start-1 row-start-1 flex h-7 items-center gap-1.5 overflow-hidden text-xs whitespace-nowrap text-muted-foreground transition-opacity duration-150 group-focus-within:opacity-0 group-hover:opacity-0">
          <span className="truncate">{a.role}</span><span>·</span><span className="font-mono">{vm.cliTag}</span><span>·</span><span>{vm.queued ? `${vm.queued} en cola` : "cola vacía"}</span>
        </div>
        <div className="pointer-events-none col-start-1 row-start-1 flex gap-1.5 opacity-0 transition-opacity duration-150 group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100">
          <button onClick={(e) => { e.stopPropagation(); onUsage(); }} title="Ver desglose de consumo"
            className="flex h-7 min-w-0 flex-1 items-center gap-2 rounded-full bg-subtle px-2.5 text-[11.5px] whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground">
            <strong className="font-mono font-medium text-foreground">{vm.cost}</strong><span>{vm.tokens} tok</span>
            <span className="h-1 min-w-6 flex-1 overflow-hidden rounded-full bg-muted"><span className="block h-full bg-muted-foreground" style={{ width: `${Math.max(vm.pctOfLimit, 1)}%` }} /></span>
            <span>{vm.queued ? `${vm.queued} en cola` : "cola vacía"}</span>
          </button>
          <button onClick={(e) => { e.stopPropagation(); onAssign(); }} aria-label={`Asignar tarea a ${a.name}`} title="Asignar tarea"
            className="grid size-7 shrink-0 place-items-center rounded-full bg-subtle text-muted-foreground hover:bg-accent hover:text-foreground"><Plus className="size-3.5" /></button>
        </div>
      </div>
    </div>
  );
}
