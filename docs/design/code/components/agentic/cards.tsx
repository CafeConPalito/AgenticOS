// components/agentic/cards.tsx — AgentCard, TaskCard, QueueCard, InboxItem, EmptyState, skeletons
import * as React from "react";
import { Check, GripVertical, ListChecks, SquareTerminal } from "lucide-react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { INBOX_META, PRIORITY_CLASS, STATUS, fmtEur, tint } from "@/lib/status";
import type { Agent, InboxRequest, Project, Status, Task } from "@/lib/types";
import { AgentAvatar, CliTag, ProjectChip, StatusBadge } from "./primitives";

/* ---------------- AgentCard ---------------- */
export function AgentCard({ agent, status, current, elapsed, queue, onOpen, onAssign }: {
  agent: Agent; status: Status; current?: { title: string; project: Project };
  elapsed?: string; queue: number; onOpen: () => void; onAssign: () => void;
}) {
  const verb = status === "waiting" ? "Esperando aprobación en" : status === "paused" ? "En pausa en" : "Trabajando en";
  return (
    <Card
      role="button" tabIndex={0} onClick={onOpen} onKeyDown={(e) => e.key === "Enter" && onOpen()}
      className={cn("cursor-pointer gap-3 rounded-lg p-3.5 shadow-none transition-colors hover:border-ring",
        status === "waiting" && "border-[color-mix(in_oklch,var(--status-waiting)_50%,var(--border))]")}
    >
      <div className="flex items-center gap-2.5">
        <AgentAvatar agent={agent} size={34} withTooltip={false} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{agent.name} <span className="font-normal text-muted-foreground">· {agent.role}</span></div>
          <div className="flex items-center gap-1.5 whitespace-nowrap text-[11.5px] text-muted-foreground">
            <span className="rounded-[3px] border px-1 font-mono text-[10px] font-bold">{agent.cli === "Claude Code" ? "CC" : "AG"}</span>{agent.cli}
          </div>
        </div>
        <StatusBadge status={status} label={status === "waiting" ? "Esperándote" : undefined} />
      </div>

      {current ? (
        <div className="flex flex-col gap-1 rounded-md border bg-subtle px-2.5 py-2">
          <span className="text-[11px] text-muted-foreground">{verb}</span>
          <span className="truncate font-medium">{current.title}</span>
          <div className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
            <span className="size-2 rounded-[2px]" style={{ background: current.project.color }} />{current.project.name}
            <span className="ml-auto font-mono text-foreground">{status === "waiting" ? `hace ${elapsed}` : elapsed}</span>
          </div>
        </div>
      ) : (
        <div className="flex min-h-[72px] items-center gap-2 rounded-md border border-dashed border-input px-2.5">
          <span className="flex-1 text-xs text-muted-foreground">Sin tarea activa</span>
          <Button size="sm" variant="outline" className="h-[26px] text-xs" onClick={(e) => { e.stopPropagation(); onAssign(); }}>Asignar tarea</Button>
        </div>
      )}

      <div className="flex gap-3.5 text-[11.5px] text-muted-foreground">
        <span>Cola <b className="font-medium text-foreground">{queue} {queue === 1 ? "tarea" : "tareas"}</b></span>
        <span>Concurrencia <b className="font-mono font-medium text-foreground">{agent.concurrency.used}/{agent.concurrency.max}</b></span>
      </div>
    </Card>
  );
}

/* ---------------- TaskCard ---------------- */
function Shimmer() {
  return <span aria-hidden className="absolute inset-x-0 top-0 h-0.5 animate-live-shimmer bg-[linear-gradient(90deg,transparent,var(--status-running),transparent)] bg-[length:200%_100%]" />;
}

export function TaskCard({ task, project, agent, showStatus, onOpen }: {
  task: Task; project: Project; agent: Agent; showStatus?: boolean; onOpen: () => void;
}) {
  return (
    <button onClick={onOpen} className="relative flex w-full flex-col gap-[7px] overflow-hidden rounded-[9px] border bg-card px-[11px] py-2.5 text-left transition-colors hover:border-ring">
      {task.status === "running" && <Shimmer />}
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <ProjectChip project={project} /><span>{task.stage}</span>
        <span className="ml-auto font-mono">{task.code}</span>
      </div>
      <div className="line-clamp-3 font-medium leading-[1.35] text-pretty">{task.title}</div>
      {showStatus && <StatusBadge status={task.status} size="xs" className="self-start" />}
      <div className="flex items-center gap-[9px] text-[11px] text-muted-foreground">
        <AgentAvatar agent={agent} size={20} />
        <span className={cn("font-medium", PRIORITY_CLASS[task.priority])}>{task.priority}</span>
        {task.subtasks[1] > 0 && <span className="flex items-center gap-[3px]"><ListChecks className="size-3" />{task.subtasks[0]}/{task.subtasks[1]}</span>}
        <span className="ml-auto font-mono">{task.elapsed ?? "—"}</span>
        {!!task.cost && <span className="font-mono text-foreground">{fmtEur(task.cost)}</span>}
      </div>
    </button>
  );
}

/** Tarjeta de la vista «Colas por agente» (sortable horizontal con @dnd-kit). */
export function QueueCard({ task, project, position, current, onOpen }: {
  task: Task; project: Project; position: number; current: boolean; onOpen: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id });
  const s = STATUS[task.status];
  return (
    <div
      ref={setNodeRef} {...attributes} {...listeners} onClick={onOpen}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("relative flex w-[230px] shrink-0 cursor-grab gap-[7px] overflow-hidden rounded-[9px] border py-[9px] pr-2.5 pl-2 hover:border-ring active:cursor-grabbing",
        current ? "border-[color-mix(in_oklch,var(--status-running)_40%,var(--border))] bg-[color-mix(in_oklch,var(--status-running)_7%,var(--card))]" : "bg-subtle",
        isDragging && "opacity-40")}
    >
      {task.status === "running" && <Shimmer />}
      <GripVertical className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="font-mono text-foreground">{current ? "Ahora" : `#${position}`}</span>
          <span className="size-[7px] rounded-[2px]" style={{ background: project.color }} />{project.name}
          <span className="ml-auto font-medium" style={{ color: `var(${s.cssVar})` }}>{s.label}</span>
        </div>
        <div className="truncate font-medium">{task.title}</div>
        <div className="text-[11px] text-muted-foreground">{task.stage} · <span className={PRIORITY_CLASS[task.priority]}>{task.priority}</span></div>
      </div>
    </div>
  );
}

/* ---------------- InboxItem ---------------- */
export function InboxItem({ req, agent, project, taskTitle, onApprove, onReject, onReply, onAck, onOpenTerminal, onOpenTask }: {
  req: InboxRequest; agent: Agent; project: Project; taskTitle: string;
  onApprove: () => void; onReject: () => void; onReply: (t: string) => void; onAck: () => void;
  onOpenTerminal: () => void; onOpenTask: () => void;
}) {
  const [text, setText] = React.useState("");
  const m = INBOX_META[req.type];
  const pending = req.status === "pending";
  return (
    <Card className="gap-0 overflow-hidden rounded-lg p-0 shadow-none">
      <div className="flex gap-3 px-4 py-3.5">
        <div className="relative">
          <AgentAvatar agent={agent} size={34} />
          <span className="absolute -right-[5px] -bottom-[5px] grid size-[18px] place-items-center rounded-full bg-card">
            <span className="size-2 rounded-full" style={{ background: `var(${m.cssVar})` }} />
          </span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-[5px]">
          <div className="flex flex-wrap items-center gap-[7px] text-xs text-muted-foreground">
            <span className="font-medium" style={{ color: `var(${m.cssVar})` }}>{m.label}</span>·
            <b className="font-medium text-foreground">{agent.name}</b>·
            <ProjectChip project={project} variant="dot" />·
            <button onClick={onOpenTask} className="text-ring hover:underline">{taskTitle}</button>
            <span className="ml-auto">{req.when}</span>
          </div>
          <h3 className="text-[15px] font-medium">{req.title}</h3>
          {req.command && (
            <code className="self-start rounded-[7px] border bg-terminal px-2.5 py-1.5 font-mono text-[13px] text-[#E6EDF7]">
              <span className="text-[#7F8DAA]">❯ </span>{req.command}
            </code>
          )}
          {req.context && <p className="text-pretty text-muted-foreground">{req.context}</p>}
          {!pending && <p className="flex items-center gap-1.5 text-[12.5px] text-status-done"><Check className="size-3.5" />{req.resolution}</p>}
        </div>
      </div>

      {pending && (
        <div className="flex flex-wrap items-center gap-2 border-t bg-subtle px-4 py-2.5">
          {req.type === "approval" && (
            <>
              <Button size="sm" onClick={onApprove} className="bg-primary-action text-white hover:bg-primary-action-hover"><Check />Aprobar</Button>
              <Button size="sm" variant="outline" onClick={onReject}>Rechazar</Button>
            </>
          )}
          {req.type === "question" && req.options?.map((o) => (
            <Button key={o} size="sm" variant="outline" className="rounded-full" onClick={() => setText(o)}>{o}</Button>
          ))}
          {(req.type === "question" || req.type === "blocked") && (
            <form className="flex min-w-[260px] flex-1 gap-1.5" onSubmit={(e) => { e.preventDefault(); if (text.trim()) onReply(text.trim()); }}>
              <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Responder con texto…" aria-label="Respuesta" className="h-[30px] bg-card" />
              <Button size="sm" type="submit" className="bg-primary-action text-white hover:bg-primary-action-hover">Responder</Button>
            </form>
          )}
          {req.type === "done" && <Button size="sm" variant="outline" onClick={onAck}>Marcar como revisado</Button>}
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onOpenTerminal}><SquareTerminal />Abrir terminal</Button>
        </div>
      )}
    </Card>
  );
}

/* ---------------- EmptyState ---------------- */
export function EmptyState({ icon: Icon, title, description, children }: {
  icon: React.ComponentType<{ className?: string }>; title: string; description?: string; children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3.5 rounded-lg border border-dashed border-input bg-subtle px-6 py-12 text-center">
      <div className="grid size-11 place-items-center rounded-lg bg-accent"><Icon className="size-[22px]" /></div>
      <div>
        <div className="text-base font-medium">{title}</div>
        {description && <div className="mt-1 text-muted-foreground">{description}</div>}
      </div>
      {children}
    </div>
  );
}

export const AGENT_TEMPLATES = [
  { name: "Analista", color: "#F27FB2" }, { name: "Desarrollador", color: "#4FD1C5" },
  { name: "QA", color: "#B5E061" }, { name: "Redactor", color: "#FFA06B" }, { name: "Comercial", color: "#8FB4FF" },
];

/* ---------------- Skeletons ---------------- */
export function AgentCardSkeleton() {
  return (
    <Card aria-busy className="h-[156px] gap-3 rounded-lg p-3.5 shadow-none">
      <div className="flex items-center gap-2.5">
        <Skeleton className="size-[34px] rounded-[9px]" />
        <div className="flex flex-1 flex-col gap-1.5"><Skeleton className="h-2.5 w-3/5" /><Skeleton className="h-2 w-1/3" /></div>
      </div>
      <Skeleton className="h-10 rounded-md" />
      <Skeleton className="h-2 w-4/5" />
    </Card>
  );
}
export function TableRowSkeleton() {
  return (
    <div className="flex items-center gap-3.5 border-b px-4 py-3.5">
      <Skeleton className="size-8 rounded-lg" /><Skeleton className="h-2.5 w-40" />
      <Skeleton className="ml-14 h-2.5 w-28" /><Skeleton className="ml-14 h-2.5 flex-1" />
    </div>
  );
}
