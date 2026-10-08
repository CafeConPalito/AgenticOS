// lib/status.ts — metadatos visuales compartidos
import type { InboxType, Priority, Status, TermLineKind } from "./types";

export const STATUS: Record<Status, { label: string; cssVar: string }> = {
  backlog: { label: "Backlog", cssVar: "--status-cancelled" },
  queued: { label: "En cola", cssVar: "--status-queued" },
  running: { label: "Ejecutando", cssVar: "--status-running" },
  waiting: { label: "Esperando humano", cssVar: "--status-waiting" },
  review: { label: "En revisión", cssVar: "--status-review" },
  done: { label: "Hecho", cssVar: "--status-done" },
  failed: { label: "Fallido", cssVar: "--status-failed" },
  cancelled: { label: "Cancelado", cssVar: "--status-cancelled" },
  idle: { label: "Inactivo", cssVar: "--status-cancelled" },
  paused: { label: "En pausa", cssVar: "--status-waiting" },
  draft: { label: "Borrador", cssVar: "--status-review" },
};

/** estilos inline de badge/tinte a partir de un token de estado */
export const tint = (cssVar: string, bg = 14, bd = 36) => ({
  color: `var(${cssVar})`,
  background: `color-mix(in oklch, var(${cssVar}) ${bg}%, transparent)`,
  borderColor: `color-mix(in oklch, var(${cssVar}) ${bd}%, transparent)`,
});

export const PRIORITY_CLASS: Record<Priority, string> = {
  Urgente: "text-status-failed", Alta: "text-status-waiting",
  Media: "text-status-queued", Baja: "text-status-cancelled",
};

export const INBOX_META: Record<InboxType, { label: string; cssVar: string }> = {
  approval: { label: "Aprobación", cssVar: "--status-waiting" },
  question: { label: "Pregunta", cssVar: "--status-running" },
  blocked: { label: "Bloqueo", cssVar: "--status-failed" },
  done: { label: "Tarea completada", cssVar: "--status-done" },
};

export const TERM_COLORS: Record<TermLineKind, string> = {
  cmd: "text-white font-bold", info: "text-[#8FB4FF]", ok: "text-[#43D392]",
  err: "text-[#FF6B6F]", edit: "text-[#F5B547]", mcp: "text-[#B39CFF]",
  dim: "text-[#7F8DAA]", sub: "text-[#4CC9F0]", user: "text-[#F5B547] font-bold",
};

export const fmtClock = (s: number) => {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = Math.floor(s % 60);
  const p = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(x)}` : `${p(m)}:${p(x)}`;
};
export const fmtEur = (n: number) => n.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
export const fmtTokens = (n: number) =>
  n >= 1e6 ? `${(n / 1e6).toLocaleString("es-ES", { maximumFractionDigits: 2 })} M`
  : n >= 1e3 ? `${(n / 1e3).toLocaleString("es-ES", { maximumFractionDigits: 1 })} k` : String(n);
