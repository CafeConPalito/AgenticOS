import type {
  Agent,
  AgentTemplate,
  CliInfo,
  MemoryNote,
  Pipeline,
  Project,
  Run,
  RunEvent,
  RunUsage,
  InboxItem,
  Breakdown,
  DailySeries,
  SessionRow,
  UsageLimits,
  UsageSummary,
  UsageToday,
  NotificationSettings,
  Task,
  TaskEvent,
  TreeNode,
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
  },
  {
    id: 'agy',
    name: 'Antigravity CLI',
    installed: false,
    path: null,
    version: null,
    models: [],
    models_error: null,
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

export function makeInboxItem(overrides: Partial<InboxItem> = {}): InboxItem {
  seq += 1
  return {
    id: `inbox-${seq}`,
    kind: 'question',
    status: 'pending',
    task_id: null,
    task_code: null,
    task_title: null,
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
  limits: UsageLimits
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
      limits: [
        {
          cli: 'claude',
          unit: 'usd',
          limit: null,
          used: 0,
          ratio: null,
          reached: false,
          near: false,
          quota_exhausted: false,
        },
        {
          cli: 'agy',
          unit: 'tokens',
          limit: null,
          used: 0,
          ratio: null,
          reached: false,
          near: false,
          quota_exhausted: false,
        },
      ],
    },
    limits: { claude_usd: null, agy_tokens: null },
  }
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
  } = {},
) {
  const usage: FakeUsage = { ...emptyUsage(), ...(seed.usage ?? {}) }

  function handleUsage(method: string, path: string, body: Record<string, unknown>) {
    if (path === '/api/settings/usage-limits') {
      if (method === 'PUT') usage.limits = body as unknown as UsageLimits
      return json(200, usage.limits)
    }
    if (path === '/api/usage/summary') return json(200, usage.summary)
    if (path === '/api/usage/daily') return json(200, usage.daily)
    if (path === '/api/usage/breakdown') return json(200, usage.breakdown)
    if (path === '/api/usage/sessions') return json(200, usage.sessions)
    if (path === '/api/usage/today') return json(200, usage.today)
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
    if (match[2] === 'dismiss') resolve(item.kind === 'delivery' ? 'reviewed' : 'dismissed')
    return json(200, item)
  }
  const tasks = [...(seed.tasks ?? [])]
  const taskEvents = { ...(seed.taskEvents ?? {}) }
  const pipelines: Record<string, Pipeline | null> = { ...(seed.pipelines ?? {}) }
  const scheduler = { paused: seed.paused ?? false }
  const agents = [...(seed.agents ?? [])]
  const projects = [...(seed.projects ?? [])]
  const runs = [...(seed.runs ?? [])]
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
    if (path === '/api/tasks') {
      if (method === 'GET') {
        const statuses = query.getAll('status')
        return json(
          200,
          tasks.filter(
            (t) =>
              (!query.get('project_id') || t.project_id === query.get('project_id')) &&
              (!query.get('agent_id') || t.agent_id === query.get('agent_id')) &&
              (!query.get('parent_task_id') || t.parent_task_id === query.get('parent_task_id')) &&
              (statuses.length === 0 || statuses.includes(t.status)),
          ),
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
    if (path.startsWith('/api/clis')) return json(200, CLIS)

    if (path === '/api/agents') {
      if (method === 'GET') return json(200, agents)
      const template = TEMPLATES.find((t) => t.id === body.template)
      const fields = omit(body, 'template')
      const agent = makeAgent({ ...(template ?? {}), ...fields, template: template?.id ?? null })
      if (template) agent.id = `agent-from-${template.id}`
      agents.push(agent)
      return json(201, agent)
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
    projects,
    runs,
    notes,
    tasks,
    inbox,
    pipelines,
    scheduler,
    usage,
    calls,
    callsTo: (method: string, path: string) =>
      calls.filter((c) => c.method === method && c.path === path),
  }
}
