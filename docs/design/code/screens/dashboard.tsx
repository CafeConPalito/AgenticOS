// screens/dashboard.tsx
import * as React from "react";
import { Bot, Hand, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AGENTS, INBOX, QUEUES, TASKS, agentById, projectById } from "@/lib/mock-data";
import { INBOX_META, STATUS, fmtClock } from "@/lib/status";
import { AgentCard, AgentCardSkeleton, AGENT_TEMPLATES, EmptyState } from "@/components/agentic/cards";
import { AgentAvatar } from "@/components/agentic/primitives";

const ACTIVITY = [
  { t: "10:42", a: "quique", txt: "pidió aprobación para ejecutar npm install -D @playwright/test", p: "tienda", k: "waiting" },
  { t: "10:39", a: "dev", txt: "lanzó el subagente tests-auth", p: "reservas", k: "running" },
  { t: "10:31", a: "quique", txt: "rechazó «Login con Google» → vuelve a Desarrollo", p: "reservas", k: "failed" },
  { t: "10:30", a: "ana", txt: "empezó «Requisitos del checkout»", p: "tienda", k: "running" },
  { t: "10:12", a: "rita", txt: "completó «Guía de estilo editorial»", p: "blog", k: "done" },
  { t: "09:58", a: "dev", txt: "añadió una nota a la memoria: «El callback valida state + PKCE»", p: "reservas", k: "review" },
] as const;
const TODAY = [{ a: "ana", v: 1.12 }, { a: "dev", v: 4.05 }, { a: "quique", v: 0.98 }, { a: "rita", v: 0.36 }];
const STARTED: Record<string, number> = { ana: 754, dev: 2471, quique: 312 }; // segundos transcurridos al cargar

function useTicker() { const [n, set] = React.useState(0); React.useEffect(() => { const i = setInterval(() => set((x) => x + 1), 1000); return () => clearInterval(i); }, []); return n; }

export function DashboardScreen({ state = "normal", onOpenTask, onOpenAgent, onNewTask, onGoInbox, onGoUsage, onArchitect }: {
  state?: "normal" | "empty" | "loading";
  onOpenTask: (id: string) => void; onOpenAgent: (id: string) => void; onNewTask: () => void;
  onGoInbox: () => void; onGoUsage: () => void; onArchitect: () => void;
}) {
  const now = useTicker();
  const pending = INBOX.filter((i) => i.status === "pending" && i.type !== "done");
  const team = AGENTS.filter((a) => !a.draft);

  return (
    <div data-screen-label="Dashboard" className="flex max-w-[1640px] flex-col gap-5 px-6 pt-[22px] pb-8">
      <div className="flex items-end gap-4">
        <div className="flex-1">
          <h1 className="text-[22px] font-medium tracking-[-0.01em]">Buenos días, Marta</h1>
          <p className="mt-[3px] text-muted-foreground">2 agentes trabajando · 1 esperándote · {INBOX.length} peticiones en el Inbox</p>
        </div>
        <span className="font-mono text-xs text-muted-foreground">jueves 8 oct · 10:43</span>
      </div>

      {state === "empty" && (
        <EmptyState icon={Bot} title="Aún no tienes agentes" description="Crea tu primer agente o usa una plantilla para empezar en un minuto.">
          <div className="flex flex-wrap justify-center gap-2">
            {AGENT_TEMPLATES.map((t) => <Button key={t.name} variant="outline" className="bg-card"><span className="size-2 rounded-[2px]" style={{ background: t.color }} />{t.name}</Button>)}
          </div>
          <Button onClick={onArchitect} className="bg-primary-action text-white hover:bg-primary-action-hover"><Sparkles />Crear con el Arquitecto</Button>
        </EmptyState>
      )}

      {state === "loading" && <div className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-3">{[0, 1, 2, 3].map((i) => <AgentCardSkeleton key={i} />)}</div>}

      {state === "normal" && (
        <>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-3">
            {team.map((a) => {
              const q = QUEUES[a.id] ?? [];
              const cur = TASKS.find((t) => t.id === q[0] && (t.status === "running" || t.status === "waiting"));
              return (
                <AgentCard key={a.id} agent={a} status={a.status}
                  current={cur && { title: cur.title, project: projectById(cur.projectId) }}
                  elapsed={fmtClock((STARTED[a.id] ?? 0) + now)} queue={q.length - (cur ? 1 : 0)}
                  onOpen={() => (cur ? onOpenTask(cur.id) : onOpenAgent(a.id))} onAssign={onNewTask} />
              );
            })}
          </div>

          <div className="grid grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] items-start gap-4">
            <div className="flex flex-col gap-4">
              {/* Aprobaciones pendientes */}
              <section className="overflow-hidden rounded-lg border border-[color-mix(in_oklch,var(--status-waiting)_45%,var(--border))] bg-card">
                <div className="flex items-center gap-2 border-b bg-[color-mix(in_oklch,var(--status-waiting)_10%,transparent)] px-3.5 py-3">
                  <Hand className="size-4 text-status-waiting" />
                  <h2 className="text-sm font-medium">Aprobaciones pendientes</h2>
                  <span className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-[#F5B547] px-1.5 text-[11px] font-bold text-[#0A1A33]">{pending.length}</span>
                  <button onClick={onGoInbox} className="ml-auto text-xs text-ring hover:underline">Ver Inbox →</button>
                </div>
                {pending.slice(0, 3).map((it) => {
                  const ag = agentById(it.agentId), pr = projectById(it.projectId), m = INBOX_META[it.type];
                  return (
                    <div key={it.id} className="flex items-center gap-3 border-b px-3.5 py-[11px] last:border-b-0">
                      <AgentAvatar agent={ag} size={26} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                          <span className="font-medium" style={{ color: `var(${m.cssVar})` }}>{m.label}</span>·<span>{ag.name}</span>·
                          <span className="size-[7px] rounded-[2px]" style={{ background: pr.color }} />{pr.name}<span className="ml-auto">{it.when}</span>
                        </div>
                        <div className="font-medium">{it.title}</div>
                        {it.command && <code className="mt-1 inline-block rounded-[5px] border bg-terminal px-[7px] py-0.5 font-mono text-xs text-[#E6EDF7]">{it.command}</code>}
                      </div>
                      {it.type === "approval" ? (
                        <div className="flex shrink-0 gap-1.5">
                          <Button size="sm" variant="outline" className="h-7" onClick={() => toast("Rechazado · " + ag.name + " buscará otra vía")}>Rechazar</Button>
                          <Button size="sm" className="h-7 bg-primary-action text-white hover:bg-primary-action-hover" onClick={() => toast.success("Aprobado · " + ag.name + " continúa")}>Aprobar</Button>
                        </div>
                      ) : <Button size="sm" variant="outline" className="h-7" onClick={onGoInbox}>Responder</Button>}
                    </div>
                  );
                })}
                {!pending.length && <p className="px-3.5 py-[18px] text-muted-foreground">Nada pendiente. Tus agentes no necesitan nada de ti ahora mismo.</p>}
              </section>

              {/* Actividad reciente */}
              <Card className="gap-2.5 rounded-lg px-4 py-3.5 shadow-none">
                <h2 className="text-sm font-medium">Actividad reciente</h2>
                <ol>
                  {ACTIVITY.map((e, i) => {
                    const ag = agentById(e.a), pr = projectById(e.p);
                    return (
                      <li key={i} className="grid min-h-[34px] grid-cols-[44px_14px_minmax(0,1fr)] items-start gap-2">
                        <span className="pt-px font-mono text-xs text-muted-foreground">{e.t}</span>
                        <span className="flex h-full flex-col items-center"><span className="mt-1 size-[9px] shrink-0 rounded-full" style={{ background: `var(${STATUS[e.k].cssVar})` }} /><span className="mt-[3px] w-px flex-1 bg-border" /></span>
                        <p className="pb-2.5"><span className="mr-[5px] inline-block size-2 rounded-[2px]" style={{ background: ag.color }} /><b className="font-medium">{ag.name}</b> {e.txt} <span className="text-xs text-muted-foreground">· {pr.name}</span></p>
                      </li>
                    );
                  })}
                </ol>
              </Card>
            </div>

            {/* Consumo de hoy */}
            <Card className="gap-3.5 rounded-lg px-4 py-3.5 shadow-none">
              <div className="flex items-center"><h2 className="flex-1 text-sm font-medium">Consumo de hoy</h2><button onClick={onGoUsage} className="text-xs text-ring hover:underline">Ver detalle →</button></div>
              <div className="grid grid-cols-2 gap-2.5">
                {[["Tokens", "3,82 M", "2,61 M en caché"], ["Coste", "6,51 €", "Límite diario 25 €"]].map(([l, v, d]) => (
                  <div key={l} className="rounded-[9px] border bg-subtle px-3 py-2.5">
                    <div className="text-[11.5px] text-muted-foreground">{l}</div>
                    <div className="font-mono text-[22px] font-medium">{v}</div>
                    <div className="text-[11px] text-muted-foreground">{d}</div>
                  </div>
                ))}
              </div>
              <div className="flex flex-col gap-[9px]">
                {TODAY.map(({ a, v }) => {
                  const ag = agentById(a);
                  return (
                    <div key={a} className="grid grid-cols-[90px_minmax(0,1fr)_56px] items-center gap-2.5 text-xs">
                      <span className="flex items-center gap-1.5"><span className="size-2 rounded-[2px]" style={{ background: ag.color }} />{ag.name}</span>
                      <span className="h-2 overflow-hidden rounded bg-muted"><span className="block h-full rounded" style={{ width: `${(v / 4.05) * 100}%`, background: ag.color }} /></span>
                      <span className="text-right font-mono">{v.toLocaleString("es-ES", { minimumFractionDigits: 2 })} €</span>
                    </div>
                  );
                })}
              </div>
              <div className="h-1.5 overflow-hidden rounded-[3px] bg-muted"><div className="h-full w-[26%] bg-primary-action" /></div>
              <p className="-mt-2 text-[11.5px] text-muted-foreground">26 % del límite diario</p>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
