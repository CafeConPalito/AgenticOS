import type {
  AgentChange,
  ArchitectMessage,
  ArchitectSettings,
  Conversation,
  Proposal,
  Sheet,
  SheetAgent,
} from '@/api/architect'

/** In-memory stand-in for the Architect's endpoints of phase 19 (plugged into the fake backend).
 * The CLI is not there: a test pushes its events with the fake WebSocket. */

const NOW = new Date().toISOString()
const REQUIRED = ['name', 'role', 'cli', 'instructions'] as const

function json(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function emptySheet(): Sheet {
  return {
    agents: {},
    existing_agents: [],
    team: {},
    pipeline: null,
    suggested_connections: [],
    base: null,
  }
}

export function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'conv-1',
    mode: 'agent',
    title: '',
    status: 'open',
    state: 'asleep',
    agent_id: null,
    team_id: null,
    project_id: null,
    proposal_id: null,
    updated_at: NOW,
    cli: null,
    model: '',
    run_id: null,
    messages: [],
    sheet: { sheet: emptySheet(), issues: [], progress: {}, ready: false, locked: [] },
    ...overrides,
  }
}

export function sheetState(agent: SheetAgent, locked: string[] = []) {
  const missing = REQUIRED.filter((key) => !agent[key])
  const filled = Object.values(agent).filter((v) => v !== undefined && v !== '').length
  return {
    sheet: { ...emptySheet(), agents: { main: agent } },
    issues: missing.map((key) => ({
      field: `main.${key}`,
      code: 'required',
      message: `Falta ${key}`,
      level: 'error' as const,
    })),
    progress: { main: Math.min(100, Math.round((100 * filled) / 11)) },
    ready: missing.length === 0,
    locked,
  }
}

export interface ArchitectSeed {
  conversations?: Conversation[]
  proposals?: Proposal[]
  /** The draft agent «Crear borrador» creates (it must exist in the fake backend's agents). */
  draftAgentId?: string
  /** The configuration history of each agent (block 8). */
  history?: Record<string, AgentChange[]>
}

export function createArchitectBackend(seed: ArchitectSeed = {}) {
  const conversations = [...(seed.conversations ?? [])]
  const proposals = [...(seed.proposals ?? [])]
  let counter = 0
  let settings: ArchitectSettings = {
    cli: '',
    account_id: '',
    model: '',
    instructions: '',
    default_instructions: '# Agente Arquitecto\n\nEres el Agente Arquitecto…',
    idle_minutes: 15,
    max_live: 2,
  }
  const find = (id: string) => conversations.find((c) => c.id === id)
  const summary = (c: Conversation) => ({
    id: c.id,
    mode: c.mode,
    title: c.title,
    status: c.status,
    state: c.state,
    agent_id: c.agent_id,
    team_id: c.team_id,
    project_id: c.project_id,
    proposal_id: c.proposal_id,
    updated_at: c.updated_at,
  })

  function handle(
    method: string,
    path: string,
    body: Record<string, unknown>,
    query: URLSearchParams = new URLSearchParams(),
  ): Response | null {
    if (path === '/api/proposals') {
      const agent = query.get('target_agent_id')
      const status = query.get('status')
      return json(
        200,
        proposals.filter(
          (p) => (!agent || p.target_agent_id === agent) && (!status || p.status === status),
        ),
      )
    }
    const history = path.match(/^\/api\/agents\/([^/]+)\/config-history$/)
    if (history) return json(200, seed.history?.[history[1]] ?? [])
    if (path === '/api/settings/architect') {
      if (method === 'PUT') settings = { ...settings, ...(body as Partial<ArchitectSettings>) }
      return json(200, settings)
    }
    if (path === '/api/architect/conversations') {
      if (method === 'GET') return json(200, conversations.map(summary))
      counter += 1
      const created = makeConversation({
        id: `conv-new-${counter}`,
        mode: (body.mode as Conversation['mode']) ?? 'agent',
        agent_id: (body.agent_id as string) ?? null,
      })
      conversations.unshift(created)
      return json(201, created)
    }
    const proposalMatch = path.match(/^\/api\/proposals\/([^/]+)(?:\/(approve|reject))?$/)
    if (proposalMatch) {
      const proposal = proposals.find((p) => p.id === proposalMatch[1])
      if (!proposal) return json(404, { detail: { code: 'proposal_not_found', message: 'nope' } })
      if (proposalMatch[2] === 'approve') {
        proposal.status = 'applied'
        return json(200, { proposal, notes: [] })
      }
      if (proposalMatch[2] === 'reject') {
        proposal.status = 'rejected'
        return json(200, proposal)
      }
      return json(200, proposal)
    }
    const match = path.match(/^\/api\/architect\/conversations\/([^/]+)(?:\/(\w+))?$/)
    if (!match) return null
    const conversation = find(match[1])
    if (!conversation)
      return json(404, { detail: { code: 'conversation_not_found', message: 'nope' } })
    const action = match[2]
    if (!action) {
      if (method === 'DELETE') {
        conversations.splice(conversations.indexOf(conversation), 1)
        return json(204, undefined)
      }
      return json(200, conversation)
    }
    if (action === 'messages') {
      const message: ArchitectMessage = {
        id: `m-${conversation.messages.length + 1}`,
        role: 'user',
        text: String(body.text),
        tool_events: [],
        created_at: NOW,
      }
      conversation.messages.push(message)
      conversation.title ||= String(body.text).split('\n')[0]
      return json(201, message)
    }
    if (action === 'sheet') {
      const agent = {
        ...(conversation.sheet.sheet.agents.main ?? {}),
        ...(body.patch as SheetAgent),
      }
      const changed = Object.keys(body.patch as SheetAgent).map((key) => `main.${key}`)
      const locked = [...new Set([...conversation.sheet.locked, ...changed])].sort()
      conversation.sheet = sheetState(agent, locked)
      return json(200, { ...conversation.sheet, refused: {} })
    }
    if (action === 'unlock') {
      const fields = body.fields as string[]
      conversation.sheet = {
        ...conversation.sheet,
        locked: conversation.sheet.locked.filter((f) => !fields.includes(f)),
      }
      return json(200, conversation.sheet)
    }
    if (action === 'propose') {
      const proposal: Proposal = {
        id: `prop-${proposals.length + 1}`,
        kind: conversation.mode === 'improve_agent' ? 'agent_changes' : 'new_agent',
        origin: 'architect',
        status: 'pending',
        reason: '',
        conversation_id: conversation.id,
        source_agent_id: null,
        source_run_id: null,
        source_task_id: null,
        target_agent_id: seed.draftAgentId ?? null,
        target_team_id: null,
        target_project_id: null,
        sheet: conversation.sheet.sheet,
        changes: [],
        new_skills: [],
        applied_fields: [],
        created_at: NOW,
        decided_at: null,
      }
      proposals.push(proposal)
      conversation.status = 'proposed'
      conversation.proposal_id = proposal.id
      conversation.agent_id = proposal.target_agent_id
      return json(201, proposal)
    }
    if (action === 'interrupt') return json(200, { interrupted: true })
    if (action === 'reset') return json(200, conversation)
    if (action === 'sleep') return json(204, undefined)
    return null
  }

  return { conversations, proposals, handle, settings: () => settings }
}
