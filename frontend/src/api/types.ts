// Mirrors backend/src/agentic_os/schemas.

export type CliId = 'claude' | 'agy'
export type PermissionMode = 'autonomous' | 'restricted' | 'ask'
export type AgentStatus = 'active' | 'draft'
export type Tool = 'read' | 'edit' | 'terminal' | 'git' | 'web' | 'browser' | 'mcp_agentic_os'
export type WorkspaceMode = 'direct' | 'worktree'

/** Files, added and deleted lines (phase 11). */
export interface ChangesTotals {
  files: number
  additions: number
  deletions: number
}

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
  /** Phase 10. Null: no team / the default account of its CLI. */
  team_id: string | null
  account_id: string | null
  /** The secondary CLI (phase 10): an account, which fixes the CLI, and a model. */
  fallback_account_id: string | null
  fallback_model: string
}

export interface Agent extends AgentFields {
  id: string
  template: string | null
  /** Running with its secondary CLI right now (the person switched). */
  using_fallback: boolean
  queued_count: number
  running_count: number
  created_at: string
  updated_at: string
}

export interface AgentTemplate extends Omit<
  AgentFields,
  'max_concurrency' | 'status' | 'team_id' | 'account_id' | 'fallback_account_id' | 'fallback_model'
> {
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
  base_branch: string | null
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

export type UsageStatus = 'pending' | 'partial' | 'final' | 'unavailable'

export interface UsageTotals {
  input_tokens: number
  output_tokens: number
  thinking_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  /** API-equivalent USD (Claude). Null when the CLI records no cost (agy). */
  cost_usd: number | null
}

export interface RunUsage extends UsageTotals {
  source: string | null
  status: UsageStatus
  cli_version: string | null
  models: Record<string, Record<string, number>>
  read_at: string | null
}

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
  /** The task (and stage) a scheduled run works on; null for a manual run. */
  task_id: string | null
  stage_id: string | null
  verdict: 'approved' | 'rejected' | null
  parent_run_id: string | null
  /** «Reanudar sesión» (phase 08): the run this one continues, and the one that continued it. */
  resumed_from_id: string | null
  resumed_by_id: string | null
  /** Its CLI conversation can be continued now. */
  resumable: boolean
  /** Its terminal log was deleted by the log retention. */
  log_purged: boolean
  /** The CLI account it ran with (phase 10) and its name. */
  account_id: string | null
  account_label: string
  /** What it changed in its folder (phase 11); null when there is no data. */
  changes: ChangesTotals | null
  task_code: string | null
  stage_name: string | null
  created_at: string
  updated_at: string
  controller: string | null
  viewers: number
  usage: RunUsage
  /** A manual run launched with an account over its daily limit, out of quota or logged out. */
  warning?: 'limit_reached' | 'quota_reached' | 'session_reached' | null
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
  /** Whether the CLI has a logged-in session; null when it cannot be told. */
  logged_in: boolean | null
  checked_at: string | null
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

export interface MemoryNote {
  id: string
  author_kind: 'agent' | 'user'
  author_name: string
  agent_id: string | null
  text: string
  created_at: string
  updated_at: string
}

export interface ProjectMemory {
  notes: MemoryNote[]
  /** Characters of the memory as the agents get it; above `limit` the oldest notes are left out. */
  size: number
  limit: number
}

export type TaskStatus =
  'backlog' | 'queued' | 'running' | 'waiting_human' | 'review' | 'done' | 'cancelled'

export const OPEN_TASK_STATUSES: TaskStatus[] = [
  'backlog',
  'queued',
  'running',
  'waiting_human',
  'review',
]

export type Priority = 'high' | 'normal' | 'low'

export type WaitingReason =
  | 'run_exited'
  | 'run_failed'
  | 'run_stopped'
  | 'interrupted'
  | 'max_rejections'
  | 'launch_failed'
  | 'no_agent'
  | 'workspace_failed'
  | 'human_request'
  | 'permission'
  | 'question_pending'
  | 'quota'

export interface Task {
  id: string
  code: string
  number: number
  project_id: string
  project_name: string
  project_color: string
  title: string
  description: string
  priority: Priority
  status: TaskStatus
  stage_id: string | null
  stage_name: string | null
  stage_index: number
  stage_count: number
  requires_review: boolean
  agent_id: string | null
  agent_name: string | null
  agent_color: string | null
  queue_position: number
  rejections: number
  waiting_reason: WaitingReason | null
  waiting_detail: string | null
  worktree_path: string | null
  branch: string | null
  /** A queued task that cannot start now even with a free agent. */
  blocked: 'folder_busy' | 'limit' | 'quota' | 'session' | 'decision' | null
  /** The account behind `limit`, `quota` and `session`. */
  blocked_by: string | null
  active_run_id: string | null
  last_run_id: string | null
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
  parent_task_id: string | null
  parent_code: string | null
  subtasks_done: number
  subtasks_total: number
  /** Every run of the task, its subagents included. */
  usage: UsageTotals
}

export type TaskEventKind =
  | 'created'
  | 'queued'
  | 'stage_started'
  | 'stage_completed'
  | 'rejected'
  | 'review_approved'
  | 'review_rejected'
  | 'waiting_human'
  | 'retried'
  | 'completed_manually'
  | 'cancelled'
  | 'done'
  | 'workspace'
  | 'human_request'
  | 'human_answered'
  | 'subtask'

export interface TaskEvent {
  id: string
  at: string
  kind: TaskEventKind
  stage_name: string | null
  agent_name: string | null
  run_id: string | null
  detail: string
}

export interface AgentQueue {
  agent_id: string
  running: Task[]
  queued: Task[]
}

export interface SchedulerState {
  paused: boolean
  queued: number
  running: number
  waiting_human: number
  review: number
}

export interface Stage {
  id: string
  position: number
  name: string
  agent_id: string | null
  agent_name: string | null
  agent_color: string | null
  requires_review: boolean
  reject_to_stage_id: string | null
  active_tasks: number
}

export interface Pipeline {
  id: string
  project_id: string
  name: string
  max_rejections: number
  stages: Stage[]
}

export interface StageWrite {
  id?: string | null
  name: string
  agent_id: string | null
  requires_review: boolean
  /** Index, in the same list, of an earlier stage the task goes back to on rejection. */
  reject_to: number | null
}

export interface PipelineWrite {
  name: string
  max_rejections: number
  stages: StageWrite[]
}

export type InboxKind =
  | 'approval'
  | 'question'
  | 'blocker'
  | 'review'
  | 'stalled'
  | 'delivery'
  | 'attention'
  | 'limit'
  | 'quota'
  | 'account'
  | 'switch'

export type InboxResolution =
  'approved' | 'rejected' | 'answered' | 'answered_in_terminal' | 'reviewed' | 'dismissed'

export interface InboxItem {
  id: string
  kind: InboxKind
  status: 'pending' | 'resolved'
  task_id: string | null
  task_code: string | null
  task_title: string | null
  /** A review or a delivery: what the task changed (phase 11); null when there is no data. */
  changes: ChangesTotals | null
  run_id: string | null
  agent_id: string | null
  agent_name: string
  agent_color: string
  project_id: string | null
  project_name: string
  project_color: string
  title: string
  detail: string
  command: string | null
  options: string[]
  response: string | null
  resolution: InboxResolution | null
  notified_at: string | null
  created_at: string
  resolved_at: string | null
}

export interface InboxSummary {
  pending: number
  resolved: number
  unnotified: InboxItem[]
}

export interface NotificationSettings {
  approval: boolean
  question: boolean
  review: boolean
  stalled: boolean
  delivery: boolean
  limits: boolean
  sound: boolean
}

export interface TreeNode {
  kind: 'run' | 'native'
  id: string
  label: string
  color: string | null
  stage_name: string | null
  status: string
  started_at: string | null
  ended_at: string | null
  children: TreeNode[]
}

// ------------------------------------------------------------------ usage (phase 07)
/** The daily limit of one account (USD for Claude Code, tokens for agy); null: none. */
export interface AccountLimit {
  account_id: string
  daily_limit: number | null
}

export interface LimitState {
  account_id: string
  account_name: string
  is_default: boolean
  cli: CliId
  unit: 'usd' | 'tokens'
  limit: number | null
  used: number
  ratio: number | null
  reached: boolean
  near: boolean
  quota_exhausted: boolean
}

export interface UsageKpis {
  cost_usd: number
  cost_change: number | null
  tokens: number
  cache_ratio: number | null
  agent_hours: number
  sessions: number
  success_ratio: number | null
}

export interface UsageSummary {
  date_from: string
  date_to: string
  kpis: UsageKpis
}

export interface UsageGroup {
  id: string
  name: string
  color: string
}

export interface DailyPoint {
  day: string
  cost: Record<string, number>
  tokens: Record<string, number>
}

export interface DailySeries {
  group: 'agent' | 'project' | 'account'
  groups: UsageGroup[]
  days: DailyPoint[]
}

export interface BreakdownRow {
  id: string | null
  name: string
  color: string
  cost_usd: number
  tokens: number
  sessions: number
  share: number | null
}

export interface Breakdown {
  group: 'agent' | 'project' | 'task' | 'account'
  rows: BreakdownRow[]
}

export interface SessionRow {
  run_id: string
  started_at: string | null
  ended_at: string | null
  duration_seconds: number | null
  agent_id: string | null
  agent_name: string
  agent_color: string
  project_id: string | null
  project_name: string
  task_id: string | null
  task_code: string | null
  task_title: string | null
  account_id: string | null
  account_label: string
  cli: CliId
  model: string
  status: RunStatus
  tokens: number
  cost_usd: number | null
  usage_status: UsageStatus
}

export interface TodayAgent {
  id: string | null
  name: string
  color: string
  cost_usd: number
  tokens: number
}

export interface UsageToday {
  day: string
  tokens: number
  cache_read_tokens: number
  cost_usd: number
  agents: TodayAgent[]
  limits: LimitState[]
}

export type AgentState = 'running' | 'waiting' | 'idle' | 'draft'

export interface HomeSession {
  run_id: string
  task_id: string | null
  task_code: string | null
  task_title: string | null
  project_id: string | null
  project_name: string
  project_color: string | null
  status: RunStatus
  resumable: boolean
  started_at: string | null
  created_at: string
}

export interface HomeAgent {
  id: string
  name: string
  role: string
  color: string
  cli: CliId
  status: AgentStatus
  state: AgentState
  team_id: string | null
  account_id: string | null
  /** Running with its secondary CLI (then `cli` and `account_id` are the secondary's). */
  using_fallback: boolean
  queued: number
  pending_requests: number
  sessions: HomeSession[]
}

export interface HomeWorker {
  agent_id: string
  agent_name: string
  task_code: string
  task_title: string
}

export interface HomeProject {
  id: string
  name: string
  color: string
  open_tasks: number
  workers: HomeWorker[]
}

export interface HomeCounts {
  sessions: number
  agents_working: number
  open_tasks: number
  active_runs: number
}

export interface Home {
  agents: HomeAgent[]
  projects: HomeProject[]
  counts: HomeCounts
}

// ------------------------------------------------------------------ accounts and teams (phase 10)
export type SessionState = 'ok' | 'down' | 'unknown'

/** A window of a subscription (5 h, weekly…) as the CLI's status line reported it. */
export interface QuotaWindow {
  /** five_hour, seven_day (Claude Code) · gemini-5h, gemini-weekly, 3p-5h, 3p-weekly (agy). */
  id: string
  used_pct: number
  resets_at: string
  read_at: string
  /** The window ended since it was read: 0 % until a session reads it again. */
  expired: boolean
}

export interface AccountAgent {
  id: string
  name: string
  color: string
}

export interface Account {
  id: string
  cli: CliId
  label: string
  /** What the UI shows: the email once known, else the label. */
  name: string
  email: string
  plan: string
  is_default: boolean
  /** The CLI's own configuration (it cannot be removed). */
  is_system: boolean
  session_state: SessionState
  session_checked_at: string | null
  daily_limit: number | null
  unit: 'usd' | 'tokens'
  used_today: number
  quota: QuotaWindow[]
  agents: AccountAgent[]
  live_runs: number
  /** A login terminal is open for it. */
  logging_in: boolean
}

export interface Team {
  id: string
  name: string
  description: string
  position: number
  agent_ids: string[]
  created_at: string
  updated_at: string
}

/** Whether Agentic OS reads agy's subscription quota (an opt-in status line in agy's settings). */
export interface AgyQuotaState {
  /** agy was run once: its settings file exists. */
  available: boolean
  enabled: boolean
  /** The person has a status line of their own: it is left alone. */
  taken: boolean
  /** An agy process is open: its settings cannot be changed now. */
  running: boolean
}
