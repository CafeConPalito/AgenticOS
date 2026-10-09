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

export interface ModelOption {
  id: string
  label: string
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
