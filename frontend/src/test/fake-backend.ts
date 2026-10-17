import type {
  AgentChangeRun,
  Changes,
  DiffLine,
  FileChange,
  FileDiff,
  RepoChanges,
} from '@/api/changes'
import type {
  BlameGroup,
  BranchInfo,
  CommitInfo,
  JobState,
  RepoOverview,
  RepoStatus,
  StatusFile,
} from '@/api/git'
import type { ProjectRepo } from '@/api/repos'
import type { ProjectBranches, ProjectSnapshots } from '@/api/maintenance'
import {
  ACTIVE_RUN_STATUSES,
  type Account,
  type AgyQuotaState,
  type Agent,
  type AgentTemplate,
  type CliInfo,
  type MemoryNote,
  type Pipeline,
  type Project,
  type Run,
  type RunEvent,
  type RunUsage,
  type InboxItem,
  type Breakdown,
  type DailySeries,
  type SessionRow,
  type LimitState,
  type Team,
  type UsageSummary,
  type UsageToday,
  type NotificationSettings,
  type Task,
  type TaskEvent,
  type TreeNode,
  type Home,
  type HomeAgent,
} from '@/api/types'

/** In-memory stand-in for the backend API, plugged into `fetch` for page tests. */

let seq = 0
const now = () => new Date().toISOString()

export function makeUsage(overrides: Partial<RunUsage> = {}): RunUsage {
  return {
    input_tokens: 0,
    output_tokens: 0,
    thinking_tokens: 0,
    cache_read_tokens: 0,
    cache_creation_tokens: 0,
    cost_usd: null,
    source: null,
    status: 'pending',
    cli_version: null,
    models: {},
    read_at: null,
    ...overrides,
  }
}

export const TEMPLATES: AgentTemplate[] = [
  {
    id: 'developer',
    name: 'Desarrollador',
    role: 'Desarrollador',
    description: 'Implementa las tareas.',
    color: '#4FD1C5',
    cli: 'claude',
    model: 'sonnet',
    instructions: '# Dev',
    permission_mode: 'autonomous',
    allowed_tools: ['read', 'edit', 'terminal'],
    can_spawn_subagents: true,
    can_create_tasks: true,
  },
  {
    id: 'qa',
    name: 'QA',
    role: 'QA',
    description: 'Verifica.',
    color: '#B5E061',
    cli: 'agy',
    model: '',
    instructions: '# QA',
    permission_mode: 'restricted',
    allowed_tools: ['read'],
    can_spawn_subagents: false,
    can_create_tasks: false,
  },
]

export const CLIS: CliInfo[] = [
  {
    id: 'claude',
    name: 'Claude Code',
    installed: true,
    path: 'C:/bin/claude.exe',
    version: '2.1.296',
    models: [
      { id: 'sonnet', label: 'Sonnet (último)' },
      { id: 'opus', label: 'Opus (último)' },
    ],
    models_error: null,
    logged_in: true,
    checked_at: '2026-10-12T10:00:00Z',
  },
  {
    id: 'agy',
    name: 'Antigravity CLI',
    installed: false,
    path: null,
    version: null,
    models: [],
    models_error: null,
    logged_in: null,
    checked_at: '2026-10-12T10:00:00Z',
  },
]

export function makeAgent(overrides: Partial<Agent> = {}): Agent {
  seq += 1
  return {
    id: `agent-${seq}`,
    name: 'Dev',
    role: 'Desarrollador',
    description: '',
    color: '#4FD1C5',
    cli: 'claude',
    model: 'sonnet',
    instructions: '',
    permission_mode: 'ask',
    allowed_tools: [],
    max_concurrency: 1,
    can_spawn_subagents: false,
    can_create_tasks: false,
    status: 'active',
    template: null,
    team_id: null,
    account_id: null,
    fallback_account_id: null,
    fallback_model: '',
    using_fallback: false,
    queued_count: 0,
    running_count: 0,
    created_at: now(),
    updated_at: now(),
    ...overrides,
  }
}

export function makeProject(overrides: Partial<Project> = {}): Project {
  seq += 1
  return {
    id: `project-${seq}`,
    name: 'Tienda online',
    color: '#7C9CFF',
    description: '',
    path: 'D:\\proyectos\\tienda',
    workspace_mode: 'direct',
    base_branch: null,
    created_at: now(),
    updated_at: now(),
    git: { is_repo: true, branch: 'main', dirty: false },
    folder_exists: true,
    ...overrides,
  }
}

/** A git repository of a project (phase 12). */
export function makeRepo(overrides: Partial<ProjectRepo> = {}): ProjectRepo {
  seq += 1
  return {
    id: `repo-${seq}`,
    project_id: 'project-1',
    name: 'web',
    path: 'D:\\proyectos\\tienda',
    rel_path: '',
    base_branch: 'main',
    participates: true,
    linked: false,
    missing: false,
    position: 0,
    pull_mode: 'ff_only',
    forge: null,
    git: { is_repo: true, branch: 'main', dirty: false },
    ...overrides,
  }
}

/** The state of a repository as the Git tab sees it (phase 12). */
export function makeRepoStatus(overrides: Partial<RepoStatus> = {}): RepoStatus {
  return {
    repo_id: null,
    branch: 'main',
    head: 'abc1234',
    detached: false,
    upstream: 'origin/main',
    ahead: 0,
    behind: 0,
    staged: [],
    unstaged: [],
    conflicts: [],
    stashes: 0,
    operation: null,
    last_fetch: null,
    clean: true,
    empty: false,
    ...overrides,
  }
}

export function makeCommit(overrides: Partial<CommitInfo> = {}): CommitInfo {
  seq += 1
  const sha = overrides.sha ?? `${seq}`.padStart(40, 'a')
  return {
    sha,
    short: sha.slice(0, 7),
    parents: [],
    author: 'Ana',
    email: 'ana@example.com',
    date: now(),
    subject: 'feat: algo',
    refs: [],
    agent_name: null,
    task_code: null,
    run_id: null,
    ...overrides,
  }
}

export function makeBranch(overrides: Partial<BranchInfo> = {}): BranchInfo {
  seq += 1
  return {
    name: 'main',
    sha: `${seq}`.padStart(40, 'b'),
    short: `${seq}`.padStart(7, 'b'),
    current: false,
    remote: false,
    upstream: null,
    ahead: 0,
    behind: 0,
    base_ahead: null,
    base_behind: null,
    last_commit: now(),
    subject: '',
    task_id: null,
    task_code: null,
    task_title: null,
    task_status: null,
    integrated: false,
    ...overrides,
  }
}

export const statusFile = (path: string, status = 'M'): StatusFile => ({
  path,
  orig_path: null,
  status,
  kind: status === '?' ? 'untracked' : 'changed',
})

export function makeRun(overrides: Partial<Run> = {}): Run {
  seq += 1
  return {
    id: `run-${seq}`,
    agent_id: 'agent-1',
    project_id: 'project-1',
    agent_name: 'Dev',
    agent_color: '#4FD1C5',
    project_name: 'Web',
    cli: 'claude',
    model: 'sonnet',
    prompt: 'Arregla el login',
    cwd: 'C:/code/web',
    status: 'running',
    activity: 'busy',
    error: null,
    cli_session_id: '0a1b2c3d-0000-4000-8000-000000000000',
    exit_code: null,
    cols: 120,
    rows: 32,
    started_at: now(),
    ended_at: null,
    summary: null,
    last_status: null,
    mcp_connected_at: null,
    task_id: null,
    stage_id: null,
    verdict: null,
    parent_run_id: null,
    resumed_from_id: null,
    resumed_by_id: null,
    resumable: false,
    log_purged: false,
    account_id: null,
    account_label: '',
    changes: null,
    task_code: null,
    stage_name: null,
    created_at: now(),
    updated_at: now(),
    controller: null,
    viewers: 0,
    usage: makeUsage(),
    ...overrides,
  }
}

export function makeNote(overrides: Partial<MemoryNote> = {}): MemoryNote {
  seq += 1
  return {
    id: `note-${seq}`,
    author_kind: 'user',
    author_name: '',
    agent_id: null,
    text: 'Usa pnpm.',
    created_at: now(),
    updated_at: now(),
    ...overrides,
  }
}

export function makeTask(overrides: Partial<Task> = {}): Task {
  seq += 1
  return {
    id: `task-${seq}`,
    code: `T-${seq}`,
    number: seq,
    project_id: 'project-1',
    project_name: 'Tienda online',
    project_color: '#7C9CFF',
    title: 'Login con Google',
    description: '',
    priority: 'normal',
    status: 'queued',
    stage_id: null,
    stage_name: null,
    stage_index: 0,
    stage_count: 0,
    requires_review: false,
    agent_id: 'agent-1',
    agent_name: 'Dev',
    agent_color: '#4FD1C5',
    queue_position: seq,
    rejections: 0,
    waiting_reason: null,
    waiting_detail: null,
    worktree_path: null,
    branch: null,
    blocked: null,
    blocked_by: null,
    active_run_id: null,
    last_run_id: null,
    queued_at: now(),
    started_at: null,
    finished_at: null,
    created_at: now(),
    updated_at: now(),
    parent_task_id: null,
    parent_code: null,
    subtasks_done: 0,
    subtasks_total: 0,
    usage: {
      input_tokens: 0,
      output_tokens: 0,
      thinking_tokens: 0,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      cost_usd: null,
    },
    ...overrides,
  }
}

export function makeAccount(overrides: Partial<Account> = {}): Account {
  seq += 1
  return {
    id: `account-${seq}`,
    cli: 'claude',
    label: '',
    name: 'Cuenta del sistema',
    email: '',
    plan: '',
    is_default: false,
    is_system: false,
    session_state: 'ok',
    session_checked_at: '2026-10-14T10:00:00Z',
    daily_limit: null,
    unit: 'usd',
    used_today: 0,
    quota: [],
    agents: [],
    live_runs: 0,
    logging_in: false,
    ...overrides,
  }
}

export function makeTeam(overrides: Partial<Team> = {}): Team {
  seq += 1
  return {
    id: `team-${seq}`,
    name: 'Producto',
    description: '',
    position: seq,
    agent_ids: [],
    created_at: now(),
    updated_at: now(),
    ...overrides,
  }
}

/** The two system accounts a fresh install has (Claude Code's and agy's). */
export function systemAccounts(): Account[] {
  return [
    makeAccount({
      id: 'account-system-claude',
      cli: 'claude',
      name: 'Cuenta del sistema',
      is_default: true,
      is_system: true,
      email: '',
    }),
    makeAccount({
      id: 'account-system-agy',
      cli: 'agy',
      name: 'Cuenta del sistema',
      unit: 'tokens',
      is_default: true,
      is_system: true,
      session_state: 'unknown',
    }),
  ]
}

export function makeInboxItem(overrides: Partial<InboxItem> = {}): InboxItem {
  seq += 1
  return {
    id: `inbox-${seq}`,
    kind: 'question',
    status: 'pending',
    task_id: null,
    task_code: null,
    task_title: null,
    changes: null,
    run_id: null,
    agent_id: 'agent-1',
    agent_name: 'Dev',
    agent_color: '#4FD1C5',
    project_id: 'project-1',
    project_name: 'Tienda online',
    project_color: '#7C9CFF',
    title: '¿Postgres o SQLite?',
    detail: '',
    command: null,
    options: [],
    response: null,
    resolution: null,
    notified_at: null,
    created_at: now(),
    resolved_at: null,
    ...overrides,
  }
}

export interface Call {
  method: string
  path: string
  query: string
  body: unknown
}

function omit(body: Record<string, unknown>, key: string): Record<string, unknown> {
  return Object.fromEntries(Object.entries(body).filter(([k]) => k !== key))
}

function json(status: number, body: unknown): Response {
  if (status === 204) return new Response(null, { status })
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function apiError(status: number, code: string, field?: string): Response {
  return json(status, { detail: { code, message: code, field } })
}

export interface FakeUsage {
  summary: UsageSummary
  daily: DailySeries
  breakdown: Breakdown
  sessions: SessionRow[]
  today: UsageToday
}

export function emptyUsage(): FakeUsage {
  return {
    summary: {
      date_from: '2026-09-13',
      date_to: '2026-10-12',
      kpis: {
        cost_usd: 0,
        cost_change: null,
        tokens: 0,
        cache_ratio: null,
        agent_hours: 0,
        sessions: 0,
        success_ratio: null,
      },
    },
    daily: { group: 'agent', groups: [], days: [] },
    breakdown: { group: 'agent', rows: [] },
    sessions: [],
    today: {
      day: '2026-10-12',
      tokens: 0,
      cache_read_tokens: 0,
      cost_usd: 0,
      agents: [],
      limits: [],
    },
  }
}

/** A changed file of a diff (phase 11). */
export function makeFileChange(overrides: Partial<FileChange> = {}): FileChange {
  return {
    path: 'src/app.py',
    old_path: null,
    status: 'modified',
    additions: 1,
    deletions: 0,
    binary: false,
    old_size: null,
    new_size: null,
    generated: false,
    ...overrides,
  }
}

/** What a test says about a diff: the header and, for a single repository, its files. */
export interface ChangesInput extends Partial<Changes> {
  files?: FileChange[]
  from_ref?: RepoChanges['from_ref']
  to_ref?: RepoChanges['to_ref']
  truncated_files?: number
  skipped_large?: number
}

/** The diff of a run or a task with one repository; the totals follow from `files` unless
 * overridden. Pass `repos` for a project with several. */
export function makeChanges(overrides: ChangesInput = {}): Changes {
  const {
    files: given,
    from_ref,
    to_ref,
    truncated_files,
    skipped_large,
    repos,
    ...rest
  } = overrides
  const files = given ?? [makeFileChange()]
  const totals = rest.totals ?? {
    files: files.length,
    additions: files.reduce((sum, f) => sum + f.additions, 0),
    deletions: files.reduce((sum, f) => sum + f.deletions, 0),
  }
  const ok = (rest.state ?? 'ok') === 'ok'
  const part: RepoChanges = {
    key: 'repo-1',
    name: 'web',
    state: 'ok',
    live: rest.live ?? false,
    partial: rest.partial ?? false,
    direct_folder: rest.direct_folder ?? false,
    from_ref: from_ref === undefined ? { kind: 'base', name: 'main' } : from_ref,
    to_ref: to_ref === undefined ? { kind: 'branch', name: 'agentic/T-1' } : to_ref,
    totals,
    files,
    truncated_files: truncated_files ?? 0,
    skipped_large: skipped_large ?? 0,
  }
  return {
    state: 'ok',
    live: false,
    partial: false,
    direct_folder: false,
    totals,
    repos: repos ?? (ok ? [part] : []),
    runs: [],
    ...rest,
  }
}

/** One repository of a diff with several. */
export function makeRepoChanges(name: string, files: FileChange[]): RepoChanges {
  return {
    key: `repo-${name}`,
    name,
    state: 'ok',
    live: false,
    partial: false,
    direct_folder: false,
    from_ref: { kind: 'base', name: 'main' },
    to_ref: { kind: 'branch', name: 'agentic/T-1' },
    totals: {
      files: files.length,
      additions: files.reduce((sum, f) => sum + f.additions, 0),
      deletions: files.reduce((sum, f) => sum + f.deletions, 0),
    },
    files,
    truncated_files: 0,
    skipped_large: 0,
  }
}

export function diffLine(
  kind: DiffLine['kind'],
  text: string,
  oldNo: number | null,
  newNo: number | null,
): DiffLine {
  return { kind, text, old_no: oldNo, new_no: newNo }
}

/** Lower case without accents, like the backend's task search. */
function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

/** One repository of the fake backend: files change side when staged or committed. */
export interface FakeRepoGit {
  status?: Partial<RepoStatus>
  branches?: BranchInfo[]
  commits?: CommitInfo[]
  blame?: BlameGroup[]
  /** The changed files, by side. */
  unstaged?: FileChange[]
  staged?: FileChange[]
  diffs?: Record<string, FileDiff>
}

export function createFakeBackend(
  seed: {
    agents?: Agent[]
    projects?: Project[]
    runs?: Run[]
    events?: RunEvent[]
    /** Memory notes by project id, oldest first. */
    notes?: Record<string, MemoryNote[]>
    tasks?: Task[]
    taskEvents?: Record<string, TaskEvent[]>
    pipelines?: Record<string, Pipeline>
    paused?: boolean
    inbox?: InboxItem[]
    trees?: Record<string, TreeNode[]>
    notificationSettings?: NotificationSettings
    usage?: Partial<FakeUsage>
    branches?: ProjectBranches[]
    clis?: CliInfo[]
    /** Overrides parts of GET /api/home; by default it is derived from the rest of the seed. */
    home?: Partial<Home>
    /** The CLI accounts (default: the two system ones). */
    accounts?: Account[]
    teams?: Team[]
    /** agy's opt-in quota line (default: available, off). */
    agyQuota?: AgyQuotaState
    /** The diffs (phase 11) by `run:<id>` or `task:<id>`: the file list, each file's diff and
     * the lines `/changes/lines` serves. Anything else answers «no snapshots». */
    /** What git says about each repository, by repository id. */
    git?: Record<string, FakeRepoGit>
    /** Repositories by project id. */
    repos?: Record<string, ProjectRepo[]>
    changes?: Record<
      string,
      { summary: Changes; diffs?: Record<string, FileDiff>; lines?: DiffLine[] }
    >
    /** What GET /api/agents/:id/changes lists. */
    agentChanges?: AgentChangeRun[]
    /** What GET /api/maintenance/snapshots lists. */
    snapshots?: ProjectSnapshots[]
  } = {},
) {
  const usage: FakeUsage = { ...emptyUsage(), ...(seed.usage ?? {}) }
  const accounts: Account[] = structuredClone(seed.accounts ?? systemAccounts())
  const teams: Team[] = structuredClone(seed.teams ?? [])
  const agyQuota: AgyQuotaState = {
    available: true,
    enabled: false,
    taken: false,
    running: false,
    ...(seed.agyQuota ?? {}),
  }

  /** The daily limits, derived from the accounts the way the backend derives them. */
  function limitStates(): LimitState[] {
    return accounts.map((account) => {
      const ratio = account.daily_limit ? account.used_today / account.daily_limit : null
      return {
        account_id: account.id,
        account_name: account.name,
        is_default: account.is_default,
        cli: account.cli,
        unit: account.unit,
        limit: account.daily_limit,
        used: account.used_today,
        ratio,
        reached: ratio !== null && ratio >= 1,
        near: ratio !== null && ratio >= 0.8,
        quota_exhausted: false,
      }
    })
  }

  function handleAccounts(
    method: string,
    path: string,
    body: Record<string, unknown>,
  ): Response | null {
    if (path === '/api/clis/agy/quota') {
      if (method === 'PUT') {
        if (!agyQuota.available) return apiError(409, 'agy_not_set_up')
        if (agyQuota.running) return apiError(409, 'agy_running')
        if (agyQuota.taken) return apiError(409, 'status_line_taken')
        agyQuota.enabled = Boolean(body.enabled)
      }
      return json(200, agyQuota)
    }
    if (path === '/api/accounts') {
      if (method === 'GET') return json(200, accounts)
      if (body.cli === 'agy') return apiError(409, 'accounts_unsupported', 'cli')
      const account = makeAccount({
        cli: body.cli as Account['cli'],
        label: String(body.label ?? ''),
        name: String(body.label ?? '') || 'Cuenta nueva',
        session_state: 'unknown',
        session_checked_at: null,
      })
      accounts.push(account)
      return json(201, account)
    }
    if (path === '/api/teams') {
      if (method === 'GET') return json(200, teams)
      const team = makeTeam({
        name: String(body.name),
        description: String(body.description ?? ''),
        agent_ids: [...((body.agent_ids as string[]) ?? [])],
      })
      moveAgents(team)
      teams.push(team)
      return json(201, team)
    }
    const teamMatch = path.match(/^\/api\/teams\/([^/]+)$/)
    if (teamMatch) {
      const index = teams.findIndex((t) => t.id === teamMatch[1])
      if (index < 0) return apiError(404, 'team_not_found')
      if (method === 'DELETE') {
        teams.splice(index, 1)
        agents.forEach((a) => {
          if (a.team_id === teamMatch[1]) a.team_id = null
        })
        return json(204, null)
      }
      const team = teams[index]
      if (typeof body.name === 'string') team.name = body.name
      if (typeof body.description === 'string') team.description = body.description
      if (Array.isArray(body.agent_ids)) {
        team.agent_ids = body.agent_ids as string[]
        moveAgents(team)
      }
      return json(200, team)
    }
    if (path === '/api/settings/switch-threshold') {
      if (method === 'PUT') switchThreshold = Number(body.threshold)
      return json(200, { threshold: switchThreshold })
    }
    if (path === '/api/settings/usage-limits') {
      if (method === 'PUT') {
        for (const entry of body.limits as { account_id: string; daily_limit: number | null }[]) {
          const account = accounts.find((a) => a.id === entry.account_id)
          if (!account) return apiError(404, 'account_not_found')
          account.daily_limit = entry.daily_limit
        }
      }
      return json(200, limitStates())
    }
    const match = path.match(/^\/api\/accounts\/([^/]+)(?:\/(default|probe|login))?$/)
    if (!match) return null
    const index = accounts.findIndex((a) => a.id === match[1])
    if (index < 0) return apiError(404, 'account_not_found')
    const account = accounts[index]
    if (match[2] === 'default') {
      accounts.forEach((a) => {
        if (a.cli === account.cli) a.is_default = a.id === account.id
      })
      return json(200, account)
    }
    if (match[2] === 'probe') {
      account.session_checked_at = now()
      return json(200, account)
    }
    if (match[2] === 'login') {
      account.logging_in = method === 'POST'
      return method === 'POST' ? json(200, account) : json(204, null)
    }
    if (method === 'PATCH') {
      if (typeof body.label === 'string') {
        account.label = body.label
        account.name = account.email || body.label
      }
      if ('daily_limit' in body) account.daily_limit = body.daily_limit as number | null
      return json(200, account)
    }
    if (account.is_system) return apiError(409, 'system_account')
    if (agents.some((a) => a.account_id === account.id)) return apiError(409, 'account_in_use')
    accounts.splice(index, 1)
    return json(204, null)
  }

  /** An agent is in one team: the members of `team` leave the one they were in. */
  function moveAgents(team: Team) {
    teams.forEach((other) => {
      if (other.id !== team.id)
        other.agent_ids = other.agent_ids.filter((id) => !team.agent_ids.includes(id))
    })
    agents.forEach((agent) => {
      if (team.agent_ids.includes(agent.id)) agent.team_id = team.id
      else if (agent.team_id === team.id) agent.team_id = null
    })
  }

  const dataDir = {
    path: 'C:\\Users\\marta\\AppData\\Roaming\\AgenticOS',
    is_default: true,
    database_bytes: 1_200_000,
    sessions_bytes: 600_000_000,
    logs_bytes: 4_000_000,
    total_bytes: 1_800_000_000,
    last_error: null as string | null,
  }

  let retention: number | null = 90
  const branches: ProjectBranches[] = structuredClone(seed.branches ?? [])

  function handleUsage(method: string, path: string, body: Record<string, unknown>) {
    if (path === '/api/settings/maintenance') {
      if (method === 'PUT') retention = body.log_retention_days as number | null
      return json(200, { log_retention_days: retention })
    }
    if (path === '/api/maintenance/logs/cleanup')
      return json(200, { runs: 3, freed_bytes: 12_500_000 })
    if (path === '/api/maintenance/branches') return json(200, branches)
    if (path === '/api/maintenance/branches/delete') {
      const project = branches.find((p) => p.project_id === body.project_id)
      const names = body.branches as string[]
      if (!project) return apiError(404, 'project_not_found')
      for (const name of names) {
        const branch = project.branches.find((b) => b.name === name)
        if (!branch) return apiError(404, 'branch_not_found')
        if (branch.in_use) return apiError(409, 'branch_in_use')
        if (!branch.merged && !body.force) return apiError(409, 'branch_not_merged')
      }
      project.branches = project.branches.filter((b) => !names.includes(b.name))
      return json(200, { deleted: names, failed: {} })
    }
    if (path === '/api/settings/data-dir') return json(200, dataDir)
    if (path === '/api/settings/data-dir/open') return json(204, null)
    if (path === '/api/settings/data-dir/move') {
      if (!String(body.to ?? '').trim()) return apiError(422, 'path_not_absolute', 'to')
      return json(202, { to: body.to, restarting: true })
    }
    if (path === '/api/usage/summary') return json(200, usage.summary)
    if (path === '/api/usage/daily') return json(200, usage.daily)
    if (path === '/api/usage/breakdown') return json(200, usage.breakdown)
    if (path === '/api/usage/sessions') return json(200, usage.sessions)
    if (path === '/api/usage/today')
      return json(200, {
        ...usage.today,
        limits: seed.usage?.today?.limits?.length ? usage.today.limits : limitStates(),
      })
    if (path === '/api/usage/sessions.csv')
      return new Response('inicio,fin', {
        status: 200,
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': 'attachment; filename="consumo_x.csv"',
        },
      })
    return null
  }

  const inbox = [...(seed.inbox ?? [])]
  const trees = { ...(seed.trees ?? {}) }
  let notificationSettings: NotificationSettings = seed.notificationSettings ?? {
    approval: true,
    question: true,
    review: true,
    stalled: true,
    delivery: false,
    limits: true,
    sound: true,
  }

  function handleInbox(
    method: string,
    path: string,
    query: URLSearchParams,
    body: Record<string, unknown>,
  ): Response | null {
    if (path === '/api/settings/notifications') {
      if (method === 'PUT') notificationSettings = body as unknown as NotificationSettings
      return json(200, notificationSettings)
    }
    if (path === '/api/inbox/summary') {
      const pending = inbox.filter((i) => i.status === 'pending')
      return json(200, {
        pending: pending.length,
        resolved: inbox.length - pending.length,
        unnotified: pending.filter((i) => !i.notified_at),
      })
    }
    if (path === '/api/inbox')
      return json(
        200,
        inbox.filter((i) => i.status === (query.get('status') ?? 'pending')),
      )
    const match = path.match(/^\/api\/inbox\/([^/]+)\/([a-z]+)$/)
    if (!match) return null
    const item = inbox.find((i) => i.id === match[1])
    if (!item) return apiError(404, 'inbox_item_not_found')
    const resolve = (resolution: InboxItem['resolution'], response: string | null = null) =>
      Object.assign(item, { status: 'resolved', resolution, response, resolved_at: now() })
    if (match[2] === 'notified') item.notified_at = now()
    if (match[2] === 'answer') resolve('answered', String(body.text))
    if (match[2] === 'approve') resolve('approved')
    if (match[2] === 'reject') resolve('rejected')
    if (match[2] === 'review')
      resolve(body.approve ? 'approved' : 'rejected', String(body.reason ?? ''))
    if (match[2] === 'resume') resolve('approved')
    if (match[2] === 'switch') {
      const agent = agents.find((a) => a.id === item.agent_id)
      if (agent && body.choice === 'switch') agent.using_fallback = true
      resolve('answered', String(body.choice))
    }
    if (match[2] === 'dismiss') resolve(item.kind === 'delivery' ? 'reviewed' : 'dismissed')
    return json(200, item)
  }
  const tasks = [...(seed.tasks ?? [])]
  const taskEvents = { ...(seed.taskEvents ?? {}) }
  const pipelines: Record<string, Pipeline | null> = { ...(seed.pipelines ?? {}) }
  const scheduler = { paused: seed.paused ?? false }
  let switchThreshold = 90
  const agents = [...(seed.agents ?? [])]
  const projects = [...(seed.projects ?? [])]
  const runs = [...(seed.runs ?? [])]

  /** GET /api/home, derived from the seed the way the backend derives it. */
  function homeFor(): Home {
    const live = runs.filter((r) => ACTIVE_RUN_STATUSES.includes(r.status) && !r.parent_run_id)
    const pending = inbox.filter((i) => i.status === 'pending')
    const agentsHome: HomeAgent[] = agents.map((agent) => {
      const own = tasks.filter((t) => t.agent_id === agent.id)
      const running = live.some((r) => r.agent_id === agent.id)
      const requests = pending.filter((i) => i.agent_id === agent.id).length
      const waiting = requests > 0 || own.some((t) => t.status === 'waiting_human')
      return {
        id: agent.id,
        name: agent.name,
        role: agent.role,
        color: agent.color,
        cli: agent.cli,
        status: agent.status,
        state:
          agent.status === 'draft' ? 'draft' : waiting ? 'waiting' : running ? 'running' : 'idle',
        team_id: agent.team_id,
        account_id: agent.account_id,
        using_fallback: agent.using_fallback,
        queued: own.filter((t) => t.status === 'queued').length,
        pending_requests: requests,
        sessions: [
          ...live.filter((r) => r.agent_id === agent.id),
          ...runs.filter((r) => r.agent_id === agent.id && r.resumable),
        ].map((r) => ({
          run_id: r.id,
          task_id: r.task_id,
          task_code: r.task_code,
          task_title: tasks.find((t) => t.id === r.task_id)?.title ?? null,
          project_id: r.project_id,
          project_name: r.project_name,
          project_color: projects.find((p) => p.id === r.project_id)?.color ?? null,
          status: r.status,
          resumable: r.resumable,
          started_at: r.started_at,
          created_at: r.created_at,
        })),
      }
    })
    const open = tasks.filter((t) => t.status !== 'done' && t.status !== 'cancelled')
    return {
      agents: agentsHome,
      projects: projects.map((p) => ({
        id: p.id,
        name: p.name,
        color: p.color,
        open_tasks: open.filter((t) => t.project_id === p.id).length,
        workers: tasks
          .filter((t) => t.project_id === p.id && t.status === 'running' && t.agent_id)
          .map((t) => ({
            agent_id: t.agent_id!,
            agent_name: t.agent_name ?? '',
            task_code: t.code,
            task_title: t.title,
          })),
      })),
      counts: {
        sessions: live.length,
        agents_working: new Set(live.map((r) => r.agent_id)).size,
        open_tasks: open.length,
        active_runs: runs.filter((r) => ACTIVE_RUN_STATUSES.includes(r.status)).length,
      },
      ...(seed.home ?? {}),
    }
  }
  const events = [...(seed.events ?? [])]
  const notes: Record<string, MemoryNote[]> = Object.fromEntries(
    Object.entries(seed.notes ?? {}).map(([id, list]) => [id, [...list]]),
  )
  const calls: Call[] = []

  function handleTasks(
    method: string,
    path: string,
    query: URLSearchParams,
    body: Record<string, unknown>,
  ): Response | null {
    if (path === '/api/scheduler' || path.startsWith('/api/scheduler/')) {
      if (path.endsWith('/pause')) scheduler.paused = true
      if (path.endsWith('/resume')) scheduler.paused = false
      const count = (status: string) => tasks.filter((t) => t.status === status).length
      return json(200, {
        paused: scheduler.paused,
        queued: count('queued'),
        running: count('running'),
        waiting_human: count('waiting_human'),
        review: count('review'),
      })
    }
    const queueMatch = path.match(/^\/api\/agents\/([^/]+)\/queue$/)
    if (queueMatch) {
      const mine = tasks.filter((t) => t.agent_id === queueMatch[1])
      if (method === 'PUT') {
        ;(body.task_ids as string[]).forEach((id, position) => {
          const task = tasks.find((t) => t.id === id)
          if (task) task.queue_position = position
        })
      }
      return json(200, {
        agent_id: queueMatch[1],
        running: mine.filter((t) => t.status === 'running'),
        queued: mine.filter((t) => t.status === 'queued'),
      })
    }
    const pipelineMatch = path.match(/^\/api\/projects\/([^/]+)\/pipeline(\/template)?$/)
    if (pipelineMatch) {
      const projectId = pipelineMatch[1]
      if (method === 'GET') return json(200, pipelines[projectId] ?? null)
      if (method === 'DELETE') {
        pipelines[projectId] = null
        return json(204, null)
      }
      type StageBody = {
        id?: string | null
        name: string
        agent_id: string | null
        requires_review: boolean
        reject_to: number | null
      }
      const stages: StageBody[] = pipelineMatch[2]
        ? [
            { name: 'Requisitos', agent_id: null, requires_review: false, reject_to: null },
            { name: 'Desarrollo', agent_id: null, requires_review: false, reject_to: null },
            { name: 'QA', agent_id: null, requires_review: false, reject_to: 1 },
          ]
        : (body.stages as StageBody[])
      const ids = stages.map((st, i) => st.id || `stage-${projectId}-${i}`)
      const pipeline: Pipeline = {
        id: `pipeline-${projectId}`,
        project_id: projectId,
        name: pipelineMatch[2] ? 'Desarrollo web' : String(body.name ?? ''),
        max_rejections: pipelineMatch[2] ? 3 : Number(body.max_rejections ?? 3),
        stages: stages.map((st, i) => {
          const agent = agents.find((a) => a.id === st.agent_id)
          return {
            id: ids[i],
            position: i,
            name: st.name,
            agent_id: st.agent_id,
            agent_name: agent?.name ?? null,
            agent_color: agent?.color ?? null,
            requires_review: st.requires_review,
            reject_to_stage_id: st.reject_to === null ? null : ids[st.reject_to],
            active_tasks: 0,
          }
        }),
      }
      pipelines[projectId] = pipeline
      return json(pipelineMatch[2] ? 201 : 200, pipeline)
    }
    if (path === '/api/home') return json(200, homeFor())
    if (path === '/api/tasks') {
      if (method === 'GET') {
        const statuses = query.getAll('status')
        const q = fold(query.get('q') ?? '')
        const found = tasks.filter(
          (t) =>
            !q ||
            fold(t.title).includes(q) ||
            fold(t.code) === q ||
            String(t.number) === q.replace(/^t-/, ''),
        )
        return json(
          200,
          found
            .filter(
              (t) =>
                (!query.get('project_id') || t.project_id === query.get('project_id')) &&
                (!query.get('agent_id') || t.agent_id === query.get('agent_id')) &&
                (!query.get('parent_task_id') ||
                  t.parent_task_id === query.get('parent_task_id')) &&
                (statuses.length === 0 || statuses.includes(t.status)),
            )
            .slice(0, Number(query.get('limit')) || undefined),
        )
      }
      const project = projects.find((p) => p.id === body.project_id)
      if (!project) return apiError(404, 'project_not_found', 'project_id')
      const first = pipelines[project.id]?.stages[0]
      if (!first && !body.agent_id) return apiError(422, 'agent_required', 'agent_id')
      const agent = agents.find((a) => a.id === (first ? first.agent_id : body.agent_id))
      const task = makeTask({
        project_id: project.id,
        project_name: project.name,
        project_color: project.color,
        title: String(body.title),
        description: String(body.description ?? ''),
        priority: (body.priority as Task['priority']) ?? 'normal',
        status: body.enqueue === false ? 'backlog' : 'queued',
        stage_id: first?.id ?? null,
        stage_name: first?.name ?? null,
        agent_id: agent?.id ?? null,
        agent_name: agent?.name ?? null,
        agent_color: agent?.color ?? null,
      })
      tasks.unshift(task)
      return json(201, task)
    }
    const treeMatch = path.match(/^\/api\/tasks\/([^/]+)\/tree$/)
    if (treeMatch) return json(200, trees[treeMatch[1]] ?? [])
    const taskMatch = path.match(/^\/api\/tasks\/([^/]+)(?:\/([a-z-]+))?$/)
    if (!taskMatch) return null
    const task = tasks.find((t) => t.id === taskMatch[1])
    if (!task) return apiError(404, 'task_not_found')
    const action = taskMatch[2]
    if (action === 'events') return json(200, taskEvents[task.id] ?? [])
    if (action === 'open-worktree') return json(204, null)
    if (action === 'retry' || action === 'enqueue' || action === 'review')
      Object.assign(task, { status: 'queued' })
    if (action === 'cancel') Object.assign(task, { status: 'cancelled', finished_at: now() })
    if (action === 'complete') Object.assign(task, { status: 'done', finished_at: now() })
    if (method === 'PATCH') Object.assign(task, body)
    return json(200, task)
  }

  function handleMemory(method: string, path: string, body: Record<string, unknown>) {
    const match = path.match(/^\/api\/projects\/([^/]+)\/memory(?:\/([^/]+))?$/)
    if (!match) return null
    if (!projects.some((p) => p.id === match[1])) return apiError(404, 'project_not_found')
    const list = (notes[match[1]] ??= [])
    if (!match[2]) {
      if (method === 'GET') {
        const size = list.reduce((n, note) => n + note.text.length + 30, 0)
        return json(200, { notes: list, size, limit: 12000 })
      }
      const note = makeNote({ text: String(body.text).trim() })
      list.push(note)
      return json(201, note)
    }
    const index = list.findIndex((n) => n.id === match[2])
    if (index < 0) return apiError(404, 'note_not_found')
    if (method === 'PATCH') {
      list[index] = { ...list[index], text: String(body.text), updated_at: now() }
      return json(200, list[index])
    }
    list.splice(index, 1)
    return json(204, null)
  }

  function handleRuns(
    method: string,
    path: string,
    query: URLSearchParams,
    body: Record<string, unknown>,
  ): Response | null {
    if (path === '/api/runs') {
      if (method === 'GET') {
        const active = query.get('active')
        return json(
          200,
          runs.filter(
            (r) =>
              (!query.get('agent_id') || r.agent_id === query.get('agent_id')) &&
              (!query.get('project_id') || r.project_id === query.get('project_id')) &&
              (active === null ||
                ['starting', 'running', 'intervening'].includes(r.status) === (active === 'true')),
          ),
        )
      }
      const agent = agents.find((a) => a.id === body.agent_id)
      const project = projects.find((p) => p.id === body.project_id)
      if (!agent) return apiError(404, 'agent_not_found', 'agent_id')
      if (!project) return apiError(404, 'project_not_found', 'project_id')
      if (!CLIS.find((c) => c.id === agent.cli)?.installed)
        return apiError(422, 'cli_not_installed', 'cli')
      const run = makeRun({
        agent_id: agent.id,
        project_id: project.id,
        agent_name: agent.name,
        agent_color: agent.color,
        project_name: project.name,
        cli: agent.cli,
        model: agent.model,
        prompt: String(body.prompt),
        cwd: project.path,
        status: 'starting',
        ...(() => {
          const account =
            accounts.find((a) => a.id === agent.account_id) ??
            accounts.find((a) => a.cli === agent.cli && a.is_default)
          return { account_id: account?.id ?? null, account_label: account?.name ?? '' }
        })(),
      })
      runs.unshift(run)
      return json(201, run)
    }
    const eventsMatch = path.match(/^\/api\/runs\/([^/]+)\/events$/)
    if (eventsMatch)
      return json(
        200,
        events.filter((e) => e.run_id === eventsMatch[1]),
      )
    const match = path.match(/^\/api\/runs\/([^/]+)(?:\/(control|stop|resume))?$/)
    if (!match) return null
    const run = runs.find((r) => r.id === match[1])
    if (!run) return apiError(404, 'run_not_found')
    if (match[2] === 'resume') {
      if (!run.resumable) return apiError(409, 'not_resumable')
      const resumed = makeRun({
        ...run,
        id: undefined,
        status: 'starting',
        ended_at: null,
        error: null,
        prompt: 'La sesión anterior se interrumpió.',
        resumed_from_id: run.id,
        resumed_by_id: null,
        resumable: false,
      })
      resumed.id = `run-resumed-${runs.length}`
      Object.assign(run, { resumable: false, resumed_by_id: resumed.id })
      const task = tasks.find((t) => t.id === run.task_id)
      if (task)
        Object.assign(task, {
          status: 'running',
          waiting_reason: null,
          active_run_id: resumed.id,
          last_run_id: resumed.id,
        })
      runs.unshift(resumed)
      return json(201, resumed)
    }
    if (match[2] === 'stop') {
      Object.assign(run, { status: 'stopped', ended_at: now(), controller: null })
      return json(202, run)
    }
    if (match[2] === 'control') {
      if (body.action === 'take') {
        if (run.controller && run.controller !== body.client_id)
          return apiError(409, 'control_taken')
        Object.assign(run, { controller: body.client_id, status: 'intervening' })
      } else if (run.controller === body.client_id) {
        Object.assign(run, { controller: null, status: 'running' })
      }
      return json(200, run)
    }
    return json(200, run)
  }

  function handle(method: string, path: string, body: Record<string, unknown>): Response {
    if (path === '/api/health')
      return json(200, { status: 'ok', name: 'Agentic OS', version: '0.1.0' })
    if (path === '/api/agent-templates') return json(200, TEMPLATES)
    if (path.startsWith('/api/clis')) return json(200, seed.clis ?? CLIS)

    if (path === '/api/agents') {
      if (method === 'GET') return json(200, agents)
      const template = TEMPLATES.find((t) => t.id === body.template)
      const fields = omit(body, 'template')
      const agent = makeAgent({ ...(template ?? {}), ...fields, template: template?.id ?? null })
      if (template) agent.id = `agent-from-${template.id}`
      agents.push(agent)
      return json(201, agent)
    }
    const clearMatch = path.match(/^\/api\/agents\/([^/]+)\/fallback\/clear$/)
    if (clearMatch) {
      const agent = agents.find((a) => a.id === clearMatch[1])
      if (!agent) return apiError(404, 'agent_not_found')
      agent.using_fallback = false
      return json(200, agent)
    }
    const agentMatch = path.match(/^\/api\/agents\/([^/]+)(\/duplicate)?$/)
    if (agentMatch) {
      const index = agents.findIndex((a) => a.id === agentMatch[1])
      if (index < 0) return apiError(404, 'agent_not_found')
      if (agentMatch[2]) {
        const copy = makeAgent({ ...agents[index], name: String(body.name) })
        copy.id = `${agents[index].id}-copy`
        agents.push(copy)
        return json(201, copy)
      }
      if (method === 'GET') return json(200, agents[index])
      if (method === 'PATCH') {
        if (body.name === '') return apiError(422, 'name_required', 'name')
        agents[index] = { ...agents[index], ...body, updated_at: now() }
        return json(200, agents[index])
      }
      agents.splice(index, 1)
      return json(204, null)
    }

    if (path === '/api/projects') {
      if (method === 'GET') return json(200, projects)
      const projectPath = String(body.path)
      if (projects.some((p) => p.path.toLowerCase() === projectPath.toLowerCase()))
        return apiError(409, 'project_exists', 'path')
      if (projectPath.includes('missing') && !body.create_folder)
        return apiError(422, 'folder_not_found', 'path')
      const fields = omit(body, 'create_folder')
      const project = makeProject({ ...fields, git: null } as Partial<Project>)
      projects.push(project)
      return json(201, project)
    }
    const projectMatch = path.match(/^\/api\/projects\/([^/]+)(\/open)?$/)
    if (projectMatch) {
      const index = projects.findIndex((p) => p.id === projectMatch[1])
      if (index < 0) return apiError(404, 'project_not_found')
      if (projectMatch[2]) return json(204, null)
      if (method === 'GET') return json(200, projects[index])
      if (method === 'PATCH') {
        projects[index] = { ...projects[index], ...body, updated_at: now() } as Project
        return json(200, projects[index])
      }
      projects.splice(index, 1)
      return json(204, null)
    }
    return apiError(404, 'not_found')
  }

  const snapshots: ProjectSnapshots[] = structuredClone(seed.snapshots ?? [])
  const NO_SNAPSHOTS: Changes = {
    state: 'no_snapshots',
    live: false,
    partial: false,
    direct_folder: false,
    totals: { files: 0, additions: 0, deletions: 0 },
    repos: [],
    runs: [],
  }

  const repos: Record<string, ProjectRepo[]> = structuredClone(seed.repos ?? {})

  function handleRepos(method: string, path: string, body: Record<string, unknown>) {
    const list = path.match(/^\/api\/projects\/([^/]+)\/repos(\/scan)?$/)
    if (list) {
      const items = (repos[list[1]] ??= [])
      if (method === 'GET' || (method === 'POST' && list[2])) return json(200, items)
      if (method === 'POST') {
        const created = makeRepo({
          project_id: list[1],
          path: String(body.path),
          name: String(body.name ?? String(body.path).split(/[\\/]/).pop()),
          rel_path: null,
          linked: true,
          position: items.length,
        })
        items.push(created)
        return json(201, created)
      }
    }
    const one = path.match(/^\/api\/repos\/([^/]+)$/)
    if (one) {
      for (const items of Object.values(repos)) {
        const index = items.findIndex((r) => r.id === one[1])
        if (index < 0) continue
        if (method === 'PATCH') {
          Object.assign(items[index], body)
          return json(200, items[index])
        }
        if (method === 'DELETE') {
          items.splice(index, 1)
          return json(204, null)
        }
      }
      return apiError(404, 'not_found')
    }
    return null
  }

  const gitState: Record<string, Required<FakeRepoGit>> = {}
  for (const [id, value] of Object.entries(seed.git ?? {}))
    gitState[id] = structuredClone({
      status: {},
      branches: [],
      commits: [],
      blame: [],
      unstaged: [],
      staged: [],
      diffs: {},
      ...value,
    })

  function statusOf(repoId: string): RepoStatus {
    const repo = gitState[repoId]
    const asFiles = (files: FileChange[]) =>
      files.map((f) => statusFile(f.path, f.status === 'added' ? 'A' : 'M'))
    const unstaged = repo.unstaged.map((f) => statusFile(f.path, f.status === 'added' ? '?' : 'M'))
    return makeRepoStatus({
      repo_id: repoId,
      ...repo.status,
      staged: asFiles(repo.staged),
      unstaged,
      clean: repo.staged.length + repo.unstaged.length === 0,
    })
  }

  function startJob(repoId: string, kind: string): JobState {
    return {
      id: `job-${calls.length}`,
      repo_id: repoId,
      kind,
      status: 'running',
      phase: '',
      percent: null,
      message: '',
      error_code: null,
      started_at: now(),
      ended_at: null,
    }
  }

  function handleGit(
    method: string,
    path: string,
    params: URLSearchParams,
    body: Record<string, unknown>,
  ) {
    const overview = path.match(/^\/api\/projects\/([^/]+)\/git\/overview$/)
    if (overview && method === 'GET') {
      const list: RepoOverview[] = (repos[overview[1]] ?? []).map((repo) => ({
        repo_id: repo.id,
        name: repo.name,
        path: repo.path,
        rel_path: repo.rel_path,
        linked: repo.linked,
        missing: repo.missing,
        base_branch: repo.base_branch,
        status: gitState[repo.id] ? statusOf(repo.id) : null,
        error: null,
      }))
      return json(200, list)
    }
    const batch = path.match(/^\/api\/projects\/([^/]+)\/git\/batch$/)
    if (batch && method === 'POST') {
      const ids = (body.repo_ids as string[]) ?? []
      return json(
        200,
        ids.map((id) => ({
          repo_id: id,
          ok: true,
          job: ['fetch', 'pull', 'push'].includes(String(body.action))
            ? startJob(id, String(body.action))
            : null,
          sha: null,
          error_code: null,
          error: null,
        })),
      )
    }
    const jobs = path.match(/^\/api\/git\/jobs\/([^/]+)$/)
    if (jobs && method === 'DELETE') return json(204, null)
    const m = path.match(/^\/api\/repos\/([^/]+)\/(.+)$/)
    if (!m || !gitState[m[1]]) return null
    const [, id, rest] = m
    const repo = gitState[id]
    if (method === 'GET') {
      if (rest === 'status') return json(200, statusOf(id))
      if (rest === 'branches') return json(200, repo.branches)
      if (rest === 'remotes') return json(200, [])
      if (rest === 'blame') return json(200, repo.blame)
      if (rest === 'log') return json(200, { commits: repo.commits, more: false })
      const commit = rest.match(/^commits\/(.+)$/)
      if (commit) {
        const found = repo.commits.find((c) => c.sha.startsWith(commit[1]))
        return found ? json(200, { ...found, body: '' }) : apiError(404, 'commit_not_found')
      }
      if (rest === 'diff' || rest === 'diff/file') {
        const kind = params.get('kind')
        if (rest === 'diff/file') {
          const diff = repo.diffs[params.get('path') ?? '']
          return diff ? json(200, diff) : apiError(404, 'file_not_found')
        }
        const staged = params.get('staged') === 'true'
        const files = kind === 'worktree' ? (staged ? repo.staged : repo.unstaged) : repo.unstaged
        return json(
          200,
          makeChanges({
            files,
            from_ref: { kind: 'head', name: '' },
            to_ref: { kind: 'worktree', name: '' },
          }),
        )
      }
    }
    if (method === 'POST') {
      const paths = (body.paths as string[]) ?? []
      if (rest === 'stage') {
        const moved = repo.unstaged.filter((f) => paths.includes(f.path))
        repo.unstaged = repo.unstaged.filter((f) => !paths.includes(f.path))
        repo.staged.push(...moved)
        return json(204, null)
      }
      if (rest === 'unstage') {
        const moved = repo.staged.filter((f) => paths.includes(f.path))
        repo.staged = repo.staged.filter((f) => !paths.includes(f.path))
        repo.unstaged.push(...moved)
        return json(204, null)
      }
      if (rest === 'discard') {
        repo.unstaged = repo.unstaged.filter((f) => !paths.includes(f.path))
        return json(204, null)
      }
      if (rest === 'commit') {
        const created = makeCommit({ subject: String(body.message).split('\n')[0] })
        repo.commits.unshift(created)
        repo.staged = []
        return json(200, { ...created, body: '' })
      }
      if (rest === 'fetch' || rest === 'pull' || rest === 'push')
        return json(202, startJob(id, rest))
      if (['apply', 'switch', 'branches', 'branches/rename', 'branches/upstream'].includes(rest))
        return json(204, null)
      if (rest === 'branches/delete') return json(200, { failed: {} })
    }
    return null
  }

  function handleChanges(method: string, path: string, params: URLSearchParams) {
    const match = path.match(/^\/api\/(runs|tasks)\/([^/]+)\/changes(?:\/(file|lines))?$/)
    if (match && method === 'GET') {
      const entry = seed.changes?.[`${match[1] === 'runs' ? 'run' : 'task'}:${match[2]}`]
      if (!entry) return match[3] ? apiError(404, 'not_found') : json(200, NO_SNAPSHOTS)
      if (!match[3]) return json(200, entry.summary)
      if (match[3] === 'file') {
        const file = params.get('path') ?? ''
        const diff = entry.diffs?.[`${params.get('repo') ?? ''}:${file}`] ?? entry.diffs?.[file]
        return diff ? json(200, diff) : apiError(404, 'file_not_found')
      }
      const start = Number(params.get('start'))
      const end = Number(params.get('end'))
      const lines = (entry.lines ?? []).filter(
        (line) => (line.new_no ?? 0) >= start && (line.new_no ?? 0) <= end,
      )
      return json(200, { lines })
    }
    const agent = path.match(/^\/api\/agents\/([^/]+)\/changes$/)
    if (agent && method === 'GET') {
      const project = params.get('project_id')
      return json(
        200,
        (seed.agentChanges ?? []).filter((run) => !project || run.project_id === project),
      )
    }
    if (path === '/api/maintenance/snapshots' && method === 'GET') return json(200, snapshots)
    const cleanup = path.match(/^\/api\/maintenance\/snapshots\/([^/]+)\/delete$/)
    if (cleanup && method === 'POST') {
      const index = snapshots.findIndex((s) => s.project_id === cleanup[1])
      if (index < 0) return apiError(404, 'project_not_found')
      const [removed] = snapshots.splice(index, 1)
      return json(200, { runs: removed.runs })
    }
    return null
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input.toString())
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
    const path = url.pathname + url.search
    calls.push({
      method,
      path: url.pathname,
      query: url.search,
      body: init?.body ? body : undefined,
    })
    return (
      handleRepos(method, url.pathname, body) ??
      handleGit(method, url.pathname, url.searchParams, body) ??
      handleChanges(method, url.pathname, url.searchParams) ??
      handleAccounts(method, url.pathname, body) ??
      handleRuns(method, url.pathname, url.searchParams, body) ??
      handleMemory(method, url.pathname, body) ??
      handleTasks(method, url.pathname, url.searchParams, body) ??
      handleInbox(method, url.pathname, url.searchParams, body) ??
      handleUsage(method, url.pathname, body) ??
      handle(method, path.split('?')[0] === '/api/clis' ? '/api/clis' : url.pathname, body)
    )
  })
  vi.stubGlobal('fetch', fetchMock)

  return {
    agents,
    accounts,
    teams,
    agyQuota,
    projects,
    runs,
    notes,
    tasks,
    inbox,
    pipelines,
    scheduler,
    usage,
    snapshots,
    repos,
    calls,
    callsTo: (method: string, path: string) =>
      calls.filter((c) => c.method === method && c.path === path),
  }
}
