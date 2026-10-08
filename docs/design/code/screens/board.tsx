// screens/board.tsx — Kanban por estado / por etapa / colas por agente
import * as React from "react";
import { DndContext, closestCenter, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, horizontalListSortingStrategy } from "@dnd-kit/sortable";
import { toast } from "sonner";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { AGENTS, PROJECTS, QUEUES, TASKS, agentById, projectById } from "@/lib/mock-data";
import { STATUS } from "@/lib/status";
import type { Status, Task } from "@/lib/types";
import { QueueCard, TaskCard } from "@/components/agentic/cards";
import { AgentAvatar } from "@/components/agentic/primitives";

type View = "estado" | "etapa" | "colas";
const COLS: Status[] = ["backlog", "queued", "running", "waiting", "review", "done"];
const STAGES = ["Requisitos", "Briefing", "Desarrollo", "Redacción", "QA", "Revisión"];

function Column({ title, color, tasks, showStatus, onOpen }: { title: string; color: string; tasks: Task[]; showStatus?: boolean; onOpen: (id: string) => void }) {
  return (
    <section className="flex min-h-0 w-[276px] shrink-0 flex-col rounded-lg border bg-subtle">
      <header className="flex items-center gap-2 px-3 pt-[11px] pb-2">
        <span className="size-2 rounded-full" style={{ background: color }} />
        <h3 className="font-medium">{title}</h3>
        <span className="font-mono text-xs text-muted-foreground">{tasks.length}</span>
      </header>
      <div className="flex flex-col gap-2 overflow-y-auto px-2 pb-2.5">
        {tasks.map((t) => <TaskCard key={t.id} task={t} project={projectById(t.projectId)} agent={agentById(t.agentId)} showStatus={showStatus} onOpen={() => onOpen(t.id)} />)}
        {!tasks.length && <div className="rounded-lg border border-dashed border-input px-2 py-4 text-center text-xs text-muted-foreground">Sin tareas</div>}
      </div>
    </section>
  );
}

export function BoardScreen({ onOpenTask }: { onOpenTask: (id: string) => void }) {
  const [view, setView] = React.useState<View>("estado");
  const [fP, setFP] = React.useState("all");
  const [fA, setFA] = React.useState("all");
  const [queues, setQueues] = React.useState(QUEUES);
  const team = AGENTS.filter((a) => !a.draft);
  const filt = TASKS.filter((t) => (fP === "all" || t.projectId === fP) && (fA === "all" || t.agentId === fA));

  const onDragEnd = (agentId: string) => ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const q = queues[agentId];
    const next = arrayMove(q, q.indexOf(String(active.id)), q.indexOf(String(over.id)));
    setQueues({ ...queues, [agentId]: next });
    const t = TASKS.find((x) => x.id === active.id)!;
    const pos = next.indexOf(t.id);
    toast(`Cola de ${agentById(agentId).name} reordenada`, { description: `«${t.title}» pasa a la posición ${pos === 0 ? "actual" : "#" + pos}` });
  };

  return (
    <div data-screen-label="Tablero" className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b px-5 py-3.5">
        <ToggleGroup type="single" value={view} onValueChange={(v) => v && setView(v as View)} className="rounded-lg border bg-muted p-[3px]">
          {[["estado", "Por estado"], ["etapa", "Por etapa"], ["colas", "Colas por agente"]].map(([v, l]) => (
            <ToggleGroupItem key={v} value={v} className="h-[26px] rounded-md px-[11px] text-[12.5px] font-medium text-muted-foreground data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-[0_1px_2px_rgba(0,0,0,.25)]">{l}</ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="h-[22px] w-px bg-border" />
        <div className="flex gap-1.5">
          {[{ id: "all", name: "Todos los proyectos", color: "" }, ...PROJECTS].map((p) => (
            <button key={p.id} onClick={() => setFP(p.id)} aria-pressed={fP === p.id}
              className={cn("flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs", fP === p.id ? "border-ring bg-accent" : "border-border")}>
              {p.color && <span className="size-2 rounded-[2px]" style={{ background: p.color }} />}{p.name}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <span className="mr-1 text-xs text-muted-foreground">Agente</span>
          <button onClick={() => setFA("all")} aria-pressed={fA === "all"} title="Todos los agentes" className={cn("grid size-7 place-items-center rounded-lg border-2 bg-muted", fA === "all" ? "border-ring" : "border-transparent")}>∗</button>
          {team.map((a) => (
            <button key={a.id} onClick={() => setFA(a.id)} aria-pressed={fA === a.id} className={cn("rounded-lg border-2", fA === a.id ? "border-ring" : "border-transparent", fA !== "all" && fA !== a.id && "opacity-45")}>
              <AgentAvatar agent={a} size={24} />
            </button>
          ))}
        </div>
      </div>

      {view !== "colas" ? (
        <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto px-5 py-4">
          {view === "estado"
            ? COLS.map((k) => <Column key={k} title={STATUS[k].label} color={`var(${STATUS[k].cssVar})`} tasks={filt.filter((t) => t.status === k)} onOpen={onOpenTask} />)
            : [...STAGES.map((s) => <Column key={s} title={s} color="var(--ring)" showStatus tasks={filt.filter((t) => t.stage === s && t.status !== "done")} onOpen={onOpenTask} />),
               <Column key="done" title="Hecho" color="var(--status-done)" tasks={filt.filter((t) => t.status === "done")} onOpen={onOpenTask} />]}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-auto px-5 py-4">
          <p className="text-xs text-muted-foreground">Arrastra las tareas para cambiar el orden en que cada agente las ejecutará. La primera tarjeta es la actual.</p>
          {team.filter((a) => fA === "all" || fA === a.id).map((a) => {
            const ids = queues[a.id].filter((id) => fP === "all" || TASKS.find((t) => t.id === id)!.projectId === fP);
            const first = TASKS.find((t) => t.id === queues[a.id][0]);
            const busy = first && (first.status === "running" || first.status === "waiting");
            return (
              <Card key={a.id} className="grid grid-cols-[190px_minmax(0,1fr)] gap-3.5 rounded-lg p-3 shadow-none">
                <div className="flex flex-col gap-1.5 border-r pr-3">
                  <div className="flex items-center gap-[9px]"><AgentAvatar agent={a} size={30} /><div><div className="font-medium">{a.name}</div><div className="text-[11.5px] text-muted-foreground">{a.role} · {a.cli === "Claude Code" ? "CC" : "AG"}</div></div></div>
                  <div className="text-[11.5px] text-muted-foreground">{busy ? "1 en curso · " : ""}{queues[a.id].length - (busy ? 1 : 0)} en cola · concurrencia <span className="font-mono text-foreground">{a.concurrency.used}/{a.concurrency.max}</span></div>
                </div>
                <DndContext collisionDetection={closestCenter} onDragEnd={onDragEnd(a.id)}>
                  <SortableContext items={ids} strategy={horizontalListSortingStrategy}>
                    <div className="flex min-h-[74px] items-stretch gap-2 overflow-x-auto">
                      {ids.map((id) => {
                        const t = TASKS.find((x) => x.id === id)!; const i = queues[a.id].indexOf(id);
                        return <QueueCard key={id} task={t} project={projectById(t.projectId)} position={i} current={i === 0 && !!busy} onOpen={() => onOpenTask(id)} />;
                      })}
                      {!ids.length && <div className="flex flex-1 items-center justify-center rounded-[9px] border border-dashed border-input text-xs text-muted-foreground">Cola vacía · {a.name} está disponible</div>}
                    </div>
                  </SortableContext>
                </DndContext>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
