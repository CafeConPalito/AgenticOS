// screens/inbox.tsx
import * as React from "react";
import { toast } from "sonner";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { INBOX, TASKS, agentById, projectById } from "@/lib/mock-data";
import type { InboxRequest } from "@/lib/types";
import { InboxItem } from "@/components/agentic/cards";

export function InboxScreen({ onOpenTask, onOpenTerminal }: { onOpenTask: (id: string) => void; onOpenTerminal: (agentId: string) => void }) {
  const [items, setItems] = React.useState<InboxRequest[]>(INBOX);
  const [filter, setFilter] = React.useState<"pending" | "resolved">("pending");
  const resolve = (id: string, resolution: string, msg: string) => {
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, status: "resolved", resolution, when: "ahora" } : x)));
    toast.success(msg);
  };
  const shown = items.filter((i) => i.status === filter);

  return (
    <div data-screen-label="Inbox" className="flex max-w-[1080px] flex-col gap-4 px-6 pt-[22px] pb-8">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <h1 className="text-[22px] font-medium">Inbox</h1>
          <p className="mt-[3px] text-muted-foreground">Peticiones de tus agentes: aprobaciones, preguntas, bloqueos y entregas.</p>
        </div>
        <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v as typeof filter)} className="rounded-lg border bg-muted p-[3px]">
          {(["pending", "resolved"] as const).map((k) => (
            <ToggleGroupItem key={k} value={k} className="h-7 gap-1.5 rounded-md px-3 text-[12.5px] font-medium text-muted-foreground data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-[0_1px_2px_rgba(0,0,0,.25)]">
              {k === "pending" ? "Pendientes" : "Resueltas"}<span className="font-mono text-[11px] text-muted-foreground">{items.filter((i) => i.status === k).length}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {shown.map((req) => {
        const ag = agentById(req.agentId);
        return (
          <InboxItem key={req.id} req={req} agent={ag} project={projectById(req.projectId)}
            taskTitle={TASKS.find((t) => t.id === req.taskId)?.title ?? ""}
            onApprove={() => resolve(req.id, "Aprobado por ti", `Aprobado · ${ag.name} continúa`)}
            onReject={() => resolve(req.id, "Rechazado por ti", `Rechazado · ${ag.name} buscará otra vía`)}
            onReply={(t) => resolve(req.id, `Respondido: «${t}»`, `Respuesta enviada a ${ag.name}`)}
            onAck={() => resolve(req.id, "Revisado", "Marcado como revisado")}
            onOpenTerminal={() => onOpenTerminal(req.agentId)} onOpenTask={() => onOpenTask(req.taskId)} />
        );
      })}

      {!shown.length && (
        <div className="rounded-lg border border-dashed border-input p-10 text-center text-muted-foreground">
          <div className="text-[15px] font-medium text-foreground">Bandeja al día</div>
          Tus agentes no necesitan nada de ti ahora mismo.
        </div>
      )}
    </div>
  );
}
