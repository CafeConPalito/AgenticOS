// components/agentic/primitives.tsx — StatusBadge, AgentAvatar, ProjectChip, CliTag, LiveDot
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { STATUS, tint } from "@/lib/status";
import type { Agent, Project, Status } from "@/lib/types";

export function LiveDot({ status, className }: { status: Status; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("size-2 shrink-0 rounded-full", status === "running" && "animate-live-pulse", className)}
      style={{ background: `var(${STATUS[status].cssVar})` }}
    />
  );
}

const BADGE_SIZE = { md: "h-[22px] px-2 text-[11px]", sm: "h-5 px-[7px] text-[11px]", xs: "h-[19px] px-[7px] text-[10.5px]" };

export function StatusBadge({ status, label, size = "md", className }: {
  status: Status; label?: string; size?: keyof typeof BADGE_SIZE; className?: string;
}) {
  const s = STATUS[status];
  return (
    <Badge variant="outline" className={cn("shrink-0 gap-1.5 rounded-full font-medium whitespace-nowrap", BADGE_SIZE[size], className)} style={tint(s.cssVar)}>
      <span aria-hidden className={cn("size-1.5 rounded-full bg-current", status === "running" && "animate-live-pulse")} />
      {label ?? s.label}
    </Badge>
  );
}

export function AgentAvatar({ agent, size = 24, withTooltip = true, className }: {
  agent: Pick<Agent, "name" | "role" | "color">; size?: number; withTooltip?: boolean; className?: string;
}) {
  const radius = size <= 16 ? 4 : size <= 24 ? 6 : size <= 34 ? 8 : 12;
  const el = (
    <span
      role="img"
      aria-label={`${agent.name} · ${agent.role}`}
      className={cn("grid shrink-0 place-items-center font-bold text-[#0A1A33] select-none", className)}
      style={{ width: size, height: size, borderRadius: radius, background: agent.color, fontSize: Math.round(size * 0.44) }}
    >
      {agent.name[0]}
    </span>
  );
  if (!withTooltip) return el;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{el}</TooltipTrigger>
      <TooltipContent>{agent.name} · {agent.role}</TooltipContent>
    </Tooltip>
  );
}

export function ProjectChip({ project, variant = "chip" }: { project: Pick<Project, "name" | "color">; variant?: "chip" | "dot" }) {
  if (variant === "dot")
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <span className="size-2 rounded-[2px]" style={{ background: project.color }} />
        {project.name}
      </span>
    );
  return (
    <span className="inline-flex h-[18px] items-center gap-1.5 rounded-[5px] px-1.5 text-[11px] text-foreground" style={{ background: `color-mix(in oklch, ${project.color} 16%, transparent)` }}>
      <span className="size-1.5 rounded-[2px]" style={{ background: project.color }} />
      {project.name}
    </span>
  );
}

/** Marcador de CLI. Sustituir el contenido por el logo oficial de cada proveedor. */
export function CliTag({ cli, size = 22 }: { cli: string; size?: number }) {
  const tag = cli === "Claude Code" ? "CC" : cli.startsWith("Antigravity") ? "AG" : cli.slice(0, 2).toUpperCase();
  return (
    <span className="grid shrink-0 place-items-center rounded-md border bg-primary font-mono font-bold text-white" style={{ width: size, height: size, fontSize: size > 26 ? 11 : 10 }} aria-label={cli}>
      {tag}
    </span>
  );
}
