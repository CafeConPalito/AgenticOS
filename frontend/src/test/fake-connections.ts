import type {
  AgentConnections,
  Connection,
  ConnectionSettings,
  ConnectionTemplate,
  ConnectionTest,
  FoundConnection,
  OAuthFlow,
  RegistrySource,
  Requirement,
  RunConnections,
  ServerDetail,
  ServerListing,
  StageConnections,
  UpdatePreview,
} from '@/api/connections'

/** In-memory stand-in for the connection endpoints of phase 18 (plugged into the fake backend). */

const NOW = new Date().toISOString()

export function makeConnection(overrides: Partial<Connection> = {}): Connection {
  const name = overrides.name ?? 'github'
  return {
    id: overrides.id ?? `conn-${name}`,
    name,
    description: 'Repositorios y pull requests.',
    icon: '',
    transport: 'http',
    command: '',
    args: [],
    cwd: '',
    url: 'https://api.example.test/mcp',
    env: {},
    headers: { Authorization: 'Bearer ${secret:GITHUB_TOKEN}' },
    secrets: [{ key: 'GITHUB_TOKEN', set: true }],
    auth: 'none',
    enabled: true,
    tools: [],
    resources: [],
    prompts: [],
    tested_at: null,
    test_error: null,
    tools_changed: false,
    tool_mode: 'all',
    allowed_tools: [],
    preapproved_tools: [],
    origin: 'user',
    revision: 1,
    assignments: [{ id: `${name}-a1`, scope: 'general', project_id: null, agent_id: null }],
    usage: { received_runs: 0, used_runs: 0, calls: 0, failed_calls: 0, last_used: null },
    oauth: null,
    registry: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  }
}

export const TOOLS = [
  {
    name: 'read_note',
    description: 'Lee una nota.',
    read_only: true,
    destructive: null,
    input_schema: {},
  },
  {
    name: 'write_note',
    description: 'Escribe una nota.',
    read_only: null,
    destructive: true,
    input_schema: {},
  },
]

export interface ConnectionsSeed {
  connections?: Connection[]
  templates?: ConnectionTemplate[]
  found?: FoundConnection[]
  /** What the next test of a connection finds (default: the two tools above). */
  testResult?: ConnectionTest['result']
  flows?: Partial<OAuthFlow>
  agent?: Record<string, AgentConnections>
  stage?: Record<string, StageConnections>
  run?: Record<string, RunConnections>
  sources?: RegistrySource[]
  listing?: ServerListing
  detail?: Record<string, ServerDetail>
  requirements?: Requirement[]
  updates?: { connection_id: string; name: string; version: string; latest: string }[]
  updatePreview?: UpdatePreview
}

function json(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function error(status: number, code: string, message = code): Response {
  return json(status, { detail: { code, message } })
}

export function createConnectionsBackend(seed: ConnectionsSeed = {}) {
  const connections = [...(seed.connections ?? [])]
  let counter = 0
  let tests = 0
  const settings: ConnectionSettings = {
    probe_timeout: 60,
    startup_timeout: 60,
    agy_grace: 5,
    oauth_port: 53682,
    registries: { official: true, smithery: true },
  }
  const sources: RegistrySource[] = seed.sources ?? [
    {
      id: 'official',
      title: 'Registro oficial de MCP',
      enabled: true,
      switchable: true,
      has_popular: true,
    },
    { id: 'smithery', title: 'Smithery', enabled: true, switchable: true, has_popular: true },
    {
      id: 'package',
      title: 'Paquete o repositorio',
      enabled: true,
      switchable: false,
      has_popular: false,
    },
  ]
  const testedWith =
    seed.testResult ??
    ({
      ok: true,
      seconds: 1.2,
      server: { name: 'probe' },
      tools: TOOLS,
      resources: [],
      prompts: [],
      error: null,
    } as NonNullable<ConnectionTest['result']>)
  const find = (id: string) => connections.find((c) => c.id === id)
  const flow: OAuthFlow = {
    id: 'flow-1',
    connection_id: '',
    state: 'waiting',
    authorization_url: 'https://auth.example.test/authorize?state=x',
    redirect_uri: 'http://127.0.0.1:53682/callback',
    error: '',
    connection: null,
    ...seed.flows,
  }
  let flowPolls = 0
  const open: string[] = []

  function handle(
    method: string,
    path: string,
    query: URLSearchParams,
    body: Record<string, unknown>,
  ): Response | null {
    if (
      !path.startsWith('/api/connections') &&
      !path.includes('/connections') &&
      path !== '/api/settings/connections'
    ) {
      return null
    }
    // --- the catalog
    if (path === '/api/connections' && method === 'GET') return json(200, connections)
    if (path === '/api/connections' && method === 'POST') {
      const names = body.json_text
        ? ['pasted-a', 'pasted-b'].slice(0, String(body.json_text).includes('two') ? 2 : 1)
        : [String(body.name)]
      if (!body.json_text && connections.some((c) => c.name === body.name)) {
        return error(409, 'name_taken', 'Ya hay una conexión con ese nombre.')
      }
      const created = names.map((name) =>
        makeConnection({
          id: `conn-new-${++counter}`,
          name,
          transport: (body.transport as Connection['transport']) ?? 'stdio',
          command: String(body.command ?? ''),
          args: (body.args as string[]) ?? [],
          env: (body.env as Record<string, string>) ?? {},
          headers: (body.headers as Record<string, string>) ?? {},
          secrets: Object.keys((body.secrets as object) ?? {}).map((key) => ({ key, set: true })),
          assignments: body.level ? [{ id: 'new-a', ...(body.level as object) } as never] : [],
        }),
      )
      connections.push(...created)
      return json(201, created)
    }
    if (path === '/api/connections/templates') {
      return json(
        200,
        seed.templates ?? [
          {
            id: 'github',
            name: 'GitHub',
            description: 'Repositorios y pull requests.',
            transport: 'http',
            auth: 'none',
            icon: 'github',
            requires: [],
            official: true,
            docs_url: '',
            command: '',
            url: 'https://api.githubcopilot.com/mcp/',
            fields: [
              {
                key: 'GITHUB_TOKEN',
                label: 'Token personal de GitHub',
                secret: true,
                required: true,
                kind: 'secret',
                help: 'Crea un token.',
                help_url: 'https://github.com/settings/tokens',
              },
            ],
          },
          {
            id: 'playwright',
            name: 'Playwright (navegador)',
            description: 'Un navegador.',
            transport: 'stdio',
            auth: 'none',
            icon: 'globe',
            requires: ['npx'],
            official: true,
            docs_url: '',
            command: 'npx -y @playwright/mcp@0.0.83',
            url: '',
            fields: [],
          },
        ],
      )
    }
    if (path === '/api/connections/from-template' && method === 'POST') {
      const created = makeConnection({
        id: `conn-new-${++counter}`,
        name: String(body.name || body.template),
        origin: 'template',
      })
      connections.push(created)
      return json(201, created)
    }
    if (path === '/api/connections/parse' && method === 'POST') {
      return json(200, {
        servers: [
          {
            name: 'pasted-a',
            transport: 'stdio',
            command: 'npx',
            args: ['-y', 'pg'],
            cwd: '',
            url: '',
            env: { PASSWORD: '${secret:PASSWORD}' },
            headers: {},
            secret_keys: ['PASSWORD'],
            ignored: ['oauth'],
          },
        ],
      })
    }
    if (path === '/api/connections/requirements') {
      return json(
        200,
        seed.requirements ?? [
          { program: 'node', found: true, path: 'C:/node.exe' },
          { program: 'npx', found: true, path: 'C:/npx.cmd' },
          { program: 'uvx', found: false, path: '' },
        ],
      )
    }
    if (path === '/api/connections/import/scan') return json(200, seed.found ?? [])
    if (path === '/api/connections/import' && method === 'POST') {
      const created = ((body.items as { id: string; name?: string }[]) ?? []).map((item) =>
        makeConnection({
          id: `conn-new-${++counter}`,
          name: item.name || item.id,
          origin: 'import',
        }),
      )
      connections.push(...created)
      return json(201, { created, problems: [] })
    }
    if (path === '/api/settings/connections') {
      if (method === 'PUT') Object.assign(settings, body)
      return json(200, settings)
    }
    // --- tests
    const startTest = path.match(/^\/api\/connections\/([^/]+)\/test$/)
    if (startTest && method === 'POST') {
      const connection = find(startTest[1])
      if (!connection) return error(404, 'connection_not_found')
      return json(202, {
        id: `test-${++tests}`,
        connection_id: connection.id,
        state: 'running',
        seconds: 0,
        result: null,
        connection: null,
      })
    }
    const testPoll = path.match(/^\/api\/connections\/tests\/([^/]+)$/)
    if (testPoll && method === 'GET') {
      const connection = connections[connections.length - 1] ?? makeConnection()
      const target = connections.find((c) => c.tools.length === 0 && !c.tested_at) ?? connection
      if (testedWith.ok) {
        target.tools = testedWith.tools
        target.tested_at = NOW
        target.test_error = null
      } else {
        target.test_error = testedWith.error
      }
      return json(200, {
        id: testPoll[1],
        connection_id: target.id,
        state: 'done',
        seconds: 1.2,
        result: testedWith,
        connection: target,
      })
    }
    if (testPoll && method === 'DELETE') return json(204, null)
    // --- the login
    const startFlow = path.match(/^\/api\/connections\/([^/]+)\/oauth\/start$/)
    if (startFlow && method === 'POST') {
      flow.connection_id = startFlow[1]
      flowPolls = 0
      return json(200, { ...flow, state: flow.state === 'done' ? 'waiting' : flow.state })
    }
    const flowPoll = path.match(/^\/api\/connections\/oauth\/flows\/([^/]+)(\/open)?$/)
    if (flowPoll && flowPoll[2] && method === 'POST') {
      open.push(flowPoll[1])
      return json(204, null)
    }
    if (flowPoll && method === 'GET') {
      flowPolls += 1
      const done = flowPolls >= 2 && !seed.flows?.state
      if (done) {
        const connection = find(flow.connection_id)
        if (connection) {
          connection.oauth = {
            status: 'connected',
            account_label: 'Linear · mcp.linear.app',
            expires_at: null,
            client_pasted: false,
            redirect_uri: flow.redirect_uri,
          }
        }
        return json(200, { ...flow, state: 'done', connection: connection ?? null })
      }
      return json(200, flow)
    }
    if (flowPoll && method === 'DELETE') return json(204, null)
    const oauthAction = path.match(/^\/api\/connections\/([^/]+)\/oauth\/(disconnect|refresh)$/)
    if (oauthAction && method === 'POST') {
      const connection = find(oauthAction[1])
      if (!connection) return error(404, 'connection_not_found')
      if (oauthAction[2] === 'disconnect' && connection.oauth)
        connection.oauth.status = 'disconnected'
      return json(200, connection)
    }
    // --- one connection
    const one = path.match(/^\/api\/connections\/([^/]+)$/)
    if (one && !['templates', 'try', 'registries'].includes(one[1])) {
      const connection = find(one[1])
      if (!connection) return error(404, 'connection_not_found')
      if (method === 'GET') return json(200, connection)
      if (method === 'PATCH') {
        const { secrets: typed, remove_secrets: removed, ...rest } = body as Record<string, unknown>
        Object.assign(connection, rest)
        for (const key of Object.keys((typed as object) ?? {})) {
          if (!connection.secrets.some((s) => s.key === key))
            connection.secrets.push({ key, set: true })
        }
        for (const key of (removed as string[]) ?? []) {
          const row = connection.secrets.find((s) => s.key === key)
          if (row) row.set = false
        }
        return json(200, connection)
      }
      if (method === 'DELETE') {
        connections.splice(connections.indexOf(connection), 1)
        return json(204, null)
      }
    }
    const exported = path.match(/^\/api\/connections\/([^/]+)\/export$/)
    if (exported) {
      return json(200, { mcpServers: { [find(exported[1])?.name ?? 'x']: { command: 'npx' } } })
    }
    // --- levels
    const assign = path.match(/^\/api\/connections\/([^/]+)\/assignments(?:\/([^/]+))?$/)
    if (assign) {
      const connection = find(assign[1])
      if (!connection) return error(404, 'connection_not_found')
      if (method === 'POST') {
        connection.assignments.push({
          id: `a-${++counter}`,
          scope: body.scope as never,
          project_id: (body.project_id as string) ?? null,
          agent_id: (body.agent_id as string) ?? null,
        })
        return json(201, connection)
      }
      if (method === 'DELETE') {
        connection.assignments = connection.assignments.filter((a) => a.id !== assign[2])
        return json(204, null)
      }
      return json(200, connection.assignments)
    }
    const agent = path.match(/^\/api\/agents\/([^/]+)\/connections$/)
    if (agent) {
      const view: AgentConnections = seed.agent?.[agent[1]] ?? {
        effective: [],
        excluded: [],
        total_tools: 0,
        total_tokens: 0,
        excluded_ids: [],
        available: [],
      }
      if (method === 'PUT') view.excluded_ids = (body.excluded as string[]) ?? []
      return json(200, view)
    }
    const stage = path.match(/^\/api\/stages\/([^/]+)\/connections$/)
    if (stage) {
      const view: StageConnections = seed.stage?.[stage[1]] ?? {
        effective: [],
        excluded: [],
        total_tools: 0,
        total_tokens: 0,
        excluded_ids: [],
        agent_id: null,
      }
      if (method === 'PUT') view.excluded_ids = (body.excluded as string[]) ?? []
      return json(200, view)
    }
    const run = path.match(/^\/api\/runs\/([^/]+)\/connections$/)
    if (run) return json(200, seed.run?.[run[1]] ?? { connections: [], calls: [] })
    // --- registries
    if (path === '/api/connections/registries') return json(200, sources)
    if (path === '/api/connections/registries/search') {
      return json(200, seed.listing ?? { cards: [], errors: {} })
    }
    if (path === '/api/connections/registries/detail') {
      const detail = seed.detail?.[`${query.get('source')}|${query.get('ref')}`]
      return detail ? json(200, detail) : error(502, 'registry_not_found', 'No está en el registro')
    }
    if (path === '/api/connections/registries/install' && method === 'POST') {
      const created = makeConnection({
        id: `conn-new-${++counter}`,
        name: String(body.name || String(body.ref).split('/').pop()),
        origin: 'registry',
      })
      connections.push(created)
      return json(201, created)
    }
    if (path === '/api/connections/updates/check') return json(200, seed.updates ?? [])
    const update = path.match(/^\/api\/connections\/([^/]+)\/update$/)
    if (update && method === 'GET') {
      return seed.updatePreview ? json(200, seed.updatePreview) : error(422, 'up_to_date')
    }
    if (update && method === 'POST') {
      const connection = find(update[1])
      if (connection?.registry) {
        connection.registry.version = connection.registry.latest_version
        connection.registry.update_available = false
      }
      return json(200, connection)
    }
    return null
  }

  return { handle, connections, opened: open }
}
