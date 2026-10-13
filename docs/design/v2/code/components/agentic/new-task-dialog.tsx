// components/agentic/new-task-dialog.tsx — «Nueva tarea» (v7: título + proyecto + agente)
import * as React from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Agent, Project } from "@/lib/types";

/** Origen: N / Ctrl+K → agente por defecto; tarjeta de agente → ese agente preseleccionado. */
export type NewTaskOrigin = { from: "shortcut" | "palette" } | { from: "agent"; agentId: string };
export interface NewTaskInput { title: string; projectId: string; agentId: string }

export function NewTaskDialog({ open, onOpenChange, origin, projects, agents, defaultAgentId = "dev", onCreate }: {
  open: boolean; onOpenChange: (o: boolean) => void; origin: NewTaskOrigin;
  projects: Project[]; agents: Agent[]; defaultAgentId?: string;
  /** Crea en estado «queued» y devuelve el código (T-161) para el toast «T-161 en la cola de Dev». */
  onCreate: (input: NewTaskInput) => void;
}) {
  const eligible = agents.filter((a) => !a.draft);
  const [title, setTitle] = React.useState("");
  const [projectId, setProjectId] = React.useState(projects[0]?.id ?? "");
  const [agentId, setAgentId] = React.useState(defaultAgentId);
  React.useEffect(() => {
    if (!open) return;
    setTitle(""); setProjectId(projects[0]?.id ?? "");
    setAgentId(origin.from === "agent" ? origin.agentId : defaultAgentId);
  }, [open, origin, projects, defaultAgentId]);

  const submit = () => { if (!title.trim()) return; onCreate({ title: title.trim(), projectId, agentId }); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-pop animate-sheet-in w-[520px] max-w-[calc(100vw-40px)] gap-0 overflow-hidden rounded-[20px] p-0 shadow-pop"
        onKeyDown={(e) => { if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") { e.preventDefault(); submit(); } }}>
        <DialogHeader className="border-b border-sep px-4 py-3.5">
          <DialogTitle className="text-[15px] font-medium">Nueva tarea</DialogTitle>
          <DialogDescription className="sr-only">Crea una tarea y ponla en la cola de un agente</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 p-4">
          <Field label="Qué hay que hacer">
            <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="p. ej. Añadir filtro por precio en categorías" className="h-9 rounded-[10px] bg-card" />
          </Field>
          <div className="grid grid-cols-2 gap-2.5">
            <Field label="Proyecto">
              <Select value={projectId} onValueChange={setProjectId}>
                <SelectTrigger className="h-9 rounded-[10px] bg-card"><SelectValue /></SelectTrigger>
                <SelectContent>{projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}><span className="mr-2 inline-block size-2 rounded-[2px]" style={{ background: p.color }} />{p.name}</SelectItem>
                ))}</SelectContent>
              </Select>
            </Field>
            <Field label="Agente">
              <Select value={agentId} onValueChange={setAgentId}>
                <SelectTrigger className="h-9 rounded-[10px] bg-card"><SelectValue /></SelectTrigger>
                <SelectContent>{eligible.map((a) => <SelectItem key={a.id} value={a.id}>{a.name} · {a.role}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
        </div>

        <DialogFooter className="gap-2 border-t border-sep px-4 py-3">
          <Button variant="outline" className="h-8 rounded-[10px]" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={submit} className="h-8 rounded-full bg-primary-action bg-[linear-gradient(180deg,rgba(255,255,255,.16),transparent)] px-3.5 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,.18),0_8px_18px_-8px_var(--primary-action)] hover:bg-primary-action-hover">
            Crear y encolar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex min-w-0 flex-col gap-[5px]"><span className="text-xs text-muted-foreground">{label}</span>{children}</label>;
}
