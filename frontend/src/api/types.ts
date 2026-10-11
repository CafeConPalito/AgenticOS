// Mirrors backend/src/agentic_os/schemas.

export type CliId = 'claude' | 'agy'
export type PermissionMode = 'autonomous' | 'restricted' | 'ask'
export type AgentStatus = 'active' | 'draft'
export type Tool = 'read' | 'edit' | 'terminal' | 'git' | 'web' | 'browser' | 'mcp_agentic_os'
export type WorkspaceMode = 'direct' | 'worktree'

export const TOOLS: Tool[] = ['read', 'edit', 'terminal', 'git', 'web', 'browser', 'mcp_agentic_os']
export const PERMISSION_MODES: PermissionMode[] = ['autonomous', 'restricted', 'ask']
export const MAX_CONCURRENCY = 5

export interface AgentFields {
  name: string
  role: string
  description: string
  color: string
  cli: CliId
  model: string
  instructions: string
  permission_mode: PermissionMode
  allowed_tools: Tool[]
  max_concurrency: number
  can_spawn_subagents: boolean
  can_create_tasks: boolean
  status: AgentStatus
}

export interface Agent extends AgentFields {
  id: string
  template: string | null
  created_at: string
  updated_at: string
}

export interface AgentTemplate extends Omit<AgentFields, 'max_concurrency' | 'status'> {
  id: string
}

export interface GitInfo {
  is_repo: boolean
  branch: string | null
  dirty: boolean
}

export interface ProjectFields {
  name: string
  color: string
  description: string
  path: string
  workspace_mode: WorkspaceMode
  memory: string
}

export interface Project extends ProjectFields {
  id: string
  created_at: string
  updated_at: string
  git: GitInfo | null
  folder_exists: boolean
}

export type RunStatus =
  | 'starting'
  | 'running'
  | 'intervening'
  | 'exited'
  | 'stopped'
  | 'completed'
  | 'failed'
  | 'interrupted'
export type RunActivity = 'busy' | 'idle'
export const ACTIVE_RUN_STATUSES: RunStatus[] = ['starting', 'running', 'intervening']

export interface Run {
  id: string
  agent_id: string | null
  project_id: string | null
  agent_name: string
  agent_color: string
  project_name: string
  cli: CliId
  model: string
  prompt: string
  cwd: string
  status: RunStatus
  activity: RunActivity
  error: string | null
  cli_session_id: string | null
  exit_code: number | null
  cols: number
  rows: number
  started_at: string | null
  ended_at: string | null
  /** Reported by the agent through the agentic-os MCP server. */
  summary: string | null
  last_status: string | null
  mcp_connected_at: string | null
  created_at: string
  updated_at: string
  controller: string | null
  viewers: number
}

export interface ModelOption {
  id: string
  /** Label from the CLI itself; null for well-known aliases named by the UI (i18n). */
  label: string | null
}

export interface CliInfo {
  id: CliId
  name: string
  installed: boolean
  path: string | null
  version: string | null
  models: ModelOption[]
  models_error: string | null
}

export type RunEventKind = 'mcp' | 'hook' | 'system'

/** What happened in a run: agentic-os MCP calls, CLI hooks and Agentic OS actions. */
export interface RunEvent {
  id: string
  run_id: string
  at: string
  kind: RunEventKind
  name: string
  detail: string
}
