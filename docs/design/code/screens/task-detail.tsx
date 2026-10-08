// screens/task-detail.tsx — Detalle de tarea / ejecución (pantalla principal)
import * as React from "react";
import { FolderGit2, Pause, Play, RotateCcw, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { RUN_TREE, TASKS, agentById, projectById } from "@/lib/mock-data";
import { STATUS, fmtClock, fmtEur } from "@/lib/status";
import { AgentAvatar, ProjectChip, StatusBadge } from "@/components/agentic/primitives";
import { RunTree, TerminalPanel } from "@/components/agentic/terminal";

const PIPELINE = [{ name: "Requisitos", agentId: "ana" }, { name: "Desarrollo", agentId: "dev" }, { name: "QA", agentId: "quique" }];
const TRANSITIONS = [
  { txt: "Requisitos → Desarrollo · aprobado por ti", when: "06/10 12:20", s: "done" },
  { txt: "Desarrollo → QA · Dev entregó 3/5 subtareas", when: "hoy 09:47", s: "review" },
  { txt: "QA → Desarrollo · rechazado por Quique: «el redirect tras el callback vuelve a /»", when: "hoy 10:31", s: "failed" },
  { txt: "Dev retoma la tarea en el worktree T-142", when: "hoy 10:01", s: "running" },
] as const;
const MCP = [
  { t: "10:43", fn: "update_status", arg: "implementando el login con Google: corrigiendo redirect" },
  { t: "10:39", fn: "spawn_subagent", arg: "tests-auth · ampliar cobertura OAuth" },
  { t: "10:22", fn: "add_memory", arg: "El callback valida state + PKCE" },
  { t: "10:14", fn: "request_approval", arg: "git push origin feature/login-google" },
  { t: "10:02", fn: "update_status", arg: "leyendo el informe de QA" },
];

function Label({ children }: { children: React.ReactNode }) { return <div className="mb-2 text-[11.5px] font-medium text-muted-foreground">{children}</div>; }

export function TaskDetailScreen({ taskId = "t1", sendToPty }: { taskId?: string; sendToPty?: (runId: string, data: string) => void }) {
  const task = TASKS.find((t) => t.id === taskId)!;
  const agent = agentById(task.agentId), project = projectById(task.projectId);
  const [paused, setPaused] = React.useState(false);
  const [intervening, setIntervening] = React.useState(false);
  const [run, setRun] = React.useState("main");
  const [now, setNow] = React.useState(0);
  const [subs, setSubs] = React.useState([
    { t: "Configurar credenciales OAuth en .env", d: true, by: "dev" }, { t: "Flujo de autorización con PKCE", d: true, by: "dev" },
    { t: "Vincular cuentas existentes por email", d: true, by: "dev" }, { t: "Corregir redirect tras callback", d: false, by: "quique" },
    { t: "Botón de Google en móvil", d: false, by: null as string | null },
  ]);
  React.useEffect(() => { if (paused) return; const i = setInterval(() => setNow((n) => n + 1), 1000); return () => clearInterval(i); }, [paused]);

  const status = paused ? "paused" : task.status;
  const stageIdx = PIPELINE.findIndex((s) => s.name === task.stage);
  const runName = run === "main" ? "dev@T-142 · cc-7f3a91" : `${run} · subagente`;

  return (
    <div data-screen-label="Detalle de tarea" className="flex h-full min-h-[560px] flex-col">
      {/* Cabecera */}
      <div className="flex items-center gap-3 border-b px-5 py-3">
        <span className="font-mono text-muted-foreground">{task.code}</span>
        <h1 className="text-[17px] font-medium">{task.title}</h1>
        <StatusBadge status={status} />
        <ProjectChip project={project} />
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><AgentAvatar agent={agent} size={20} />{agent.name} · {agent.role}</span>
        <div className="ml-auto flex gap-1.5">
          <Button variant="outline" size="sm" onClick={() => { setPaused(!paused); toast(paused ? "Ejecución reanudada" : "Ejecución en pausa"); }}>{paused ? <Play /> : <Pause />}{paused ? "Reanudar" : "Pausar"}</Button>
          <Button variant="outline" size="sm" onClick={() => toast("Reintento programado", { description: "Nueva sesión en el mismo worktree" })}><RotateCcw />Reintentar</Button>
          <Button variant="outline" size="sm" onClick={() => toast("Abriendo worktree en el Explorador", { description: "D:\\proyectos\\app-reservas.wt\\T-142" })}><FolderGit2 />Abrir worktree</Button>
          <Button variant="outline" size="sm" className="border-[color-mix(in_oklch,var(--status-failed)_50%,transparent)] bg-transparent text-status-failed hover:bg-[color-mix(in_oklch,var(--status-failed)_12%,transparent)] hover:text-status-failed"
            onClick={() => toast("¿Cancelar la ejecución?", { description: "Se detendrá Dev y sus 2 subagentes", action: { label: "Confirmar", onClick: () => toast.error("Ejecución cancelada") } })}><Square />Cancelar</Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_316px] grid-rows-[minmax(0,1fr)]">
        {/* Izquierda */}
        <aside className="flex flex-col gap-[18px] overflow-y-auto border-r p-4">
          <div><Label>Descripción</Label><p className="text-pretty">Permitir que los clientes inicien sesión con su cuenta de Google (OAuth 2.0 + PKCE). Si el email ya existe, vincular la cuenta. Redirigir al panel tras el login.</p></div>
          <div>
            <Label>Etapa del pipeline</Label>
            <ol className="flex items-center gap-1">
              {PIPELINE.map((s, i) => (
                <React.Fragment key={s.name}>
                  {i > 0 && <span className="h-px min-w-2 flex-1 bg-border" />}
                  <li className={cn("flex h-6 items-center gap-[5px] rounded-full border px-2 text-[11.5px] whitespace-nowrap",
                    i === stageIdx ? "border-status-running bg-[color-mix(in_oklch,var(--status-running)_14%,transparent)]" : "border-border", i < stageIdx && "text-muted-foreground")}
                    aria-current={i === stageIdx ? "step" : undefined}>
                    <AgentAvatar agent={agentById(s.agentId)} size={16} withTooltip={false} />{s.name}
                  </li>
                </React.Fragment>
              ))}
            </ol>
          </div>
          <div>
            <Label>Subtareas · {subs.filter((s) => s.d).length}/{subs.length}</Label>
            {subs.map((s, i) => (
              <label key={i} className="flex cursor-pointer items-start gap-2 rounded-md px-1.5 py-[5px] hover:bg-accent">
                <Checkbox checked={s.d} onCheckedChange={() => setSubs(subs.map((x, j) => (j === i ? { ...x, d: !x.d } : x)))} className="mt-0.5" />
                <span className={cn("flex-1", s.d && "text-muted-foreground line-through")}>{s.t}</span>
                {s.by && <span className="font-mono text-[10.5px] text-muted-foreground">@{s.by}</span>}
              </label>
            ))}
          </div>
          <div>
            <Label>Historial de transiciones</Label>
            <ol className="flex flex-col gap-[9px]">
              {TRANSITIONS.map((t, i) => (
                <li key={i} className="flex gap-2 text-xs"><span className="mt-[5px] size-2 shrink-0 rounded-full" style={{ background: `var(${STATUS[t.s].cssVar})` }} /><div><div>{t.txt}</div><div className="text-[11px] text-muted-foreground">{t.when}</div></div></li>
              ))}
            </ol>
          </div>
          <div className="rounded-[9px] border bg-subtle px-3 py-2.5">
            <Label>Resumen del agente</Label>
            <p className="text-[12.5px] text-pretty">Flujo OAuth implementado en <code className="font-mono">src/auth/google.ts</code>. Corregido el redirect que QA marcó como fallido. Pendiente: botón en móvil y documentar variables de entorno.</p>
          </div>
        </aside>

        {/* Centro: terminal en vivo */}
        <TerminalPanel
          title={runName} intervening={intervening}
          onTakeControl={() => setIntervening(true)}
          onGiveBack={() => { setIntervening(false); toast("Control devuelto a Dev", { description: "Tus comandos quedan en el historial de la sesión" }); }}
          onData={(d) => sendToPty?.(run, d)}
          workingLabel={paused ? "⏸ Ejecución en pausa" : "Dev está trabajando…"}
          footer={<><span>xterm · 132×38</span><span>pwsh 7.4</span><span>D:\proyectos\app-reservas.wt\T-142</span><span className="ml-auto">rama feature/login-google</span></>}
        />

        {/* Derecha */}
        <aside className="flex flex-col gap-[18px] overflow-y-auto border-l p-4">
          <div><Label>Árbol de ejecución</Label><RunTree root={RUN_TREE} selected={run} onSelect={(id) => { setRun(id); setIntervening(false); }} now={paused ? 0 : now} /></div>
          <div>
            <Label>Eventos MCP</Label>
            <ol className="flex flex-col gap-2">
              {MCP.map((m, i) => (
                <li key={i} className="grid grid-cols-[40px_minmax(0,1fr)] gap-2 text-xs">
                  <span className="font-mono text-muted-foreground">{m.t}</span>
                  <span><span className="font-mono text-status-review">{m.fn}</span><span className="text-muted-foreground">: </span>{m.arg}</span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <Label>Consumo de la sesión</Label>
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[9px] border bg-border">
              {[["Tokens entrada", "1,24 M"], ["Tokens salida", "86,4 k"], ["Caché (lectura)", "3,10 M"], ["Caché (escritura)", "212 k"],
                ["Coste", fmtEur(2.84 + now * 0.0011)], ["Duración", fmtClock(2471 + now)]].map(([l, v]) => (
                <div key={l} className="bg-card px-2.5 py-2"><dt className="text-[11px] text-muted-foreground">{l}</dt><dd className="font-mono text-sm">{v}</dd></div>
              ))}
            </dl>
            <p className="mt-2 flex items-center gap-1.5 text-[11.5px] text-muted-foreground">ID de sesión <code className="rounded bg-muted px-[5px] py-px font-mono text-foreground">cc-7f3a91e2-04b8</code></p>
          </div>
        </aside>
      </div>
    </div>
  );
}
