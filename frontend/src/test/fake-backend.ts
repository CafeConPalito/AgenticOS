import type { Agent, AgentTemplate, CliInfo, Project, Run } from '@/api/types'

/** In-memory stand-in for the backend API, plugged into `fetch` for page tests. */

let seq = 0
const now = () => new Date().toISOString()

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
    memory: '',
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
    created_at: now(),
    updated_at: now(),
    controller: null,
    viewers: 0,
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

export function createFakeBackend(
  seed: { agents?: Agent[]; projects?: Project[]; runs?: Run[] } = {},
) {
  const agents = [...(seed.agents ?? [])]
  const projects = [...(seed.projects ?? [])]
  const runs = [...(seed.runs ?? [])]
  const calls: Call[] = []

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
    const match = path.match(/^\/api\/runs\/([^/]+)(?:\/(control|stop))?$/)
    if (!match) return null
    const run = runs.find((r) => r.id === match[1])
    if (!run) return apiError(404, 'run_not_found')
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
      handle(method, path.split('?')[0] === '/api/clis' ? '/api/clis' : url.pathname, body)
    )
  })
  vi.stubGlobal('fetch', fetchMock)

  return {
    agents,
    projects,
    runs,
    calls,
    callsTo: (method: string, path: string) =>
      calls.filter((c) => c.method === method && c.path === path),
  }
}
