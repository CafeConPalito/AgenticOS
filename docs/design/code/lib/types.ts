// lib/types.ts
export type Status =
  | "backlog" | "queued" | "running" | "waiting" | "review"
  | "done" | "failed" | "cancelled" | "idle" | "paused" | "draft";

export type Cli = "Claude Code" | "Antigravity";
export type PermissionMode = "Autónomo" | "Restringido" | "Preguntar";
export type Priority = "Urgente" | "Alta" | "Media" | "Baja";

export interface Agent {
  id: string; name: string; role: string; color: string;
  cli: Cli; model: string; permission: PermissionMode;
  status: Status; concurrency: { used: number; max: number };
  monthCost: number; description: string; draft?: boolean;
}
export interface Project {
  id: string; name: string; color: string; path: string;
  branch: string | null; pipeline: string; workspace: "folder" | "worktree";
}
export interface Task {
  id: string; code: string; title: string; projectId: string; stage: string;
  agentId: string; status: Status; priority: Priority;
  subtasks: [done: number, total: number]; elapsed?: string; cost?: number;
}
export type InboxType = "approval" | "question" | "blocked" | "done";
export interface InboxRequest {
  id: string; type: InboxType; agentId: string; projectId: string; taskId: string;
  title: string; command?: string; context?: string; options?: string[];
  when: string; status: "pending" | "resolved"; resolution?: string;
}
export interface Run { id: string; name: string; status: Status; durationSec: number; children?: Run[] }
export interface PipelineStage { id: string; name: string; agentId: string }
export type TermLineKind = "cmd" | "info" | "ok" | "err" | "edit" | "mcp" | "dim" | "sub" | "user";
export interface TermLine { kind: TermLineKind; text: string }
