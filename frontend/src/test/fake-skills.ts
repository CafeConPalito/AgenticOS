import type {
  CliSkill,
  DiffFile,
  Listing,
  Proposal,
  Registry,
  RegistryPreview,
  RunSkill,
  Skill,
  SkillDetail,
  SkillFile,
  SkillModeRow,
  SkillOriginInfo,
  SkillSettings,
  SkillVersion,
  StatsRow,
  StatsRun,
  TryResult,
} from '@/api/skills'

/** In-memory stand-in for the skill endpoints of phase 17 (plugged into the fake backend). */

const NOW = new Date().toISOString()

export function makeSkill(overrides: Partial<SkillDetail> = {}): SkillDetail {
  const name = overrides.name ?? 'revision-codigo'
  return {
    id: overrides.id ?? `skill-${name}`,
    name,
    description: 'Revisa los cambios de una rama.',
    scope: 'general',
    project_id: null,
    agent_id: null,
    enabled: true,
    review: 'none',
    origin: 'user',
    version: 1,
    tokens: 120,
    files: 1,
    executables: 0,
    model_invocable: true,
    used: 0,
    last_used: null,
    created_at: NOW,
    updated_at: NOW,
    body: '# Pasos\n1. Lee el diff.',
    header: { name, description: overrides.description ?? 'Revisa los cambios de una rama.' },
    file_list: [{ path: 'SKILL.md', size: 120, executable: false }],
    versions: 1,
    ...overrides,
  }
}

export function makeVersion(overrides: Partial<SkillVersion> = {}): SkillVersion {
  return {
    id: 'v1',
    number: 1,
    status: 'accepted',
    description: 'Revisa los cambios de una rama.',
    tokens: 120,
    files: 1,
    note: 'Creada',
    author: {
      kind: 'user',
      label: 'Tú',
      agent_id: null,
      run_id: null,
      task_id: null,
      task_title: '',
    },
    base_version_id: null,
    restored_from_id: null,
    created_at: NOW,
    decided_at: null,
    current: true,
    ...overrides,
  }
}

export interface SkillsSeed {
  skills?: SkillDetail[]
  versions?: Record<string, SkillVersion[]>
  /** Text of a file by `skillId/path` (or `preview:<id>/path`). */
  fileTexts?: Record<string, string>
  diffs?: Record<string, DiffFile[]>
  cliSkills?: CliSkill[]
  agentModes?: Record<string, SkillModeRow[]>
  stageModes?: Record<string, SkillModeRow[]>
  tryResult?: TryResult
  runSkills?: Record<string, RunSkill[]>
  proposals?: Proposal[]
  registries?: Registry[]
  popular?: Listing
  search?: Listing
  preview?: RegistryPreview
  origins?: Record<string, SkillOriginInfo>
  stats?: StatsRow[]
  daily?: { day: string; loads: Record<string, number> }[]
  statsRuns?: StatsRun[]
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

const summary = (detail: SkillDetail): Skill => {
  const { body: _b, header: _h, file_list: _f, versions: _v, ...skill } = detail
  void _b
  void _h
  void _f
  void _v
  return skill
}

export function createSkillsBackend(seed: SkillsSeed = {}) {
  const skills = [...(seed.skills ?? [])]
  const versions: Record<string, SkillVersion[]> = { ...(seed.versions ?? {}) }
  const files: Record<string, string> = { ...(seed.fileTexts ?? {}) }
  const proposals = [...(seed.proposals ?? [])]
  const agentModes = { ...(seed.agentModes ?? {}) }
  const stageModes = { ...(seed.stageModes ?? {}) }
  const settings: SkillSettings = {
    candidates: 5,
    index_tokens: 600,
    always_tokens: 6000,
    words_floor: 0.15,
    proposals_enabled: true,
    proposals_per_run: 1,
    registries: { skills_sh: true, anthropic: true, skillsmp: false, clawhub: false },
    skillsmp_key_set: false,
  }
  const accepted: { versionId: string; body: Record<string, unknown> }[] = []
  const installed: Record<string, unknown>[] = []
  let counter = 0

  const find = (id: string) => skills.find((s) => s.id === id)
  const versionsOf = (id: string) => (versions[id] ??= [makeVersion({ id: `${id}-v1` })])

  function newVersion(skill: SkillDetail, note: string, kind: SkillVersion['author']['kind']) {
    const list = versionsOf(skill.id).map((v) => ({ ...v, current: false }))
    const number = (skill.version ?? 0) + 1
    const version = makeVersion({
      id: `${skill.id}-v${number}`,
      number,
      note,
      author: { ...makeVersion().author, kind },
    })
    versions[skill.id] = [version, ...list]
    skill.version = number
    skill.versions = number
    return version
  }

  function handle(
    method: string,
    path: string,
    query: URLSearchParams,
    body: Record<string, unknown>,
  ): Response | null {
    // --- library
    if (path === '/api/skills' && method === 'GET') {
      const scope = query.get('scope')
      return json(
        200,
        skills
          .filter((s) => !scope || s.scope === scope)
          .filter((s) => !query.get('project_id') || s.project_id === query.get('project_id'))
          .filter((s) => !query.get('agent_id') || s.agent_id === query.get('agent_id'))
          .map(summary),
      )
    }
    if (path === '/api/skills' && method === 'POST') {
      const name = String(body.name)
      if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(name)) return error(422, 'bad_name')
      const skill = makeSkill({
        id: `skill-new-${++counter}`,
        name,
        description: String(body.description),
        body: String(body.body ?? ''),
        scope: body.scope as Skill['scope'],
        project_id: (body.project_id as string) ?? null,
        agent_id: (body.agent_id as string) ?? null,
        file_list: [
          { path: 'SKILL.md', size: 100, executable: false },
          ...Object.keys((body.files as object) ?? {}).map((p) => ({
            path: p,
            size: 10,
            executable: /\.(py|sh)$/.test(p),
          })),
        ],
      })
      skills.push(skill)
      return json(201, skill)
    }
    if (path === '/api/skills/cli-scan') return json(200, seed.cliSkills ?? [])
    if (path === '/api/skills/cli-import') {
      const items = (body.items as { path: string }[]) ?? []
      return json(
        201,
        items.map((item) => {
          const name = item.path.split(/[\\/]/).pop() ?? 'x'
          const skill = makeSkill({ id: `skill-imp-${++counter}`, name, origin: 'import' })
          skills.push(skill)
          return {
            path: item.path,
            skill: summary(skill),
            renamed_to: null,
            error_code: null,
            message: null,
          }
        }),
      )
    }
    if (path === '/api/skills/import') {
      const name = String(body.path).split(/[\\/]/).pop() ?? 'x'
      const skill = makeSkill({ id: `skill-imp-${++counter}`, name, origin: 'import' })
      skills.push(skill)
      return json(201, {
        path: body.path,
        skill: summary(skill),
        renamed_to: null,
        error_code: null,
        message: null,
      })
    }
    if (path === '/api/skills/try') {
      return json(
        200,
        seed.tryResult ?? {
          method: 'words',
          always: [],
          candidates: [],
          excluded: [],
          section: '',
        },
      )
    }
    // --- proposals
    if (path === '/api/skills/proposals/pending') return json(200, proposals)
    let match = path.match(/^\/api\/skills\/proposals\/([^/]+)(?:\/(accept|reject))?$/)
    if (match) {
      const proposal = proposals.find((p) => p.version.id === match![1])
      if (!proposal) return error(409, 'not_proposed')
      if (!match[2]) return json(200, proposal)
      proposals.splice(proposals.indexOf(proposal), 1)
      if (match[2] === 'reject') return json(204, null)
      const opened = new Set((body.opened_files as string[]) ?? [])
      if (proposal.executables.some((p) => !opened.has(p))) {
        proposals.push(proposal)
        return error(409, 'scripts_not_opened')
      }
      accepted.push({ versionId: match[1], body })
      const skill = makeSkill({ ...proposal.skill, review: 'none', body: proposal.body })
      skills.push(skill)
      return json(200, skill)
    }
    if (path === '/api/settings/skills') {
      if (method === 'PUT') {
        const { skillsmp_key, ...rest } = body as Record<string, unknown>
        Object.assign(settings, rest)
        if (typeof skillsmp_key === 'string') settings.skillsmp_key_set = !!skillsmp_key
      }
      return json(200, settings)
    }
    // --- registries
    if (path === '/api/skills/registries') return json(200, seed.registries ?? [])
    if (path === '/api/skills/registries/popular')
      return json(200, seed.popular ?? { cards: [], errors: {}, attribution: '' })
    if (path === '/api/skills/registries/search')
      return json(200, seed.search ?? { cards: [], errors: {}, attribution: '' })
    if (path === '/api/skills/registries/preview') {
      return seed.preview ? json(200, seed.preview) : error(502, 'registry_offline')
    }
    match = path.match(/^\/api\/skills\/registries\/previews\/([^/]+)\/files\/(.+)$/)
    if (match)
      return new Response(files[`preview:${match[1]}/${match[2]}`] ?? 'contenido', { status: 200 })
    if (path === '/api/skills/registries/install') {
      const preview = seed.preview!
      const opened = new Set((body.opened_files as string[]) ?? [])
      if (preview.executables.some((p) => !opened.has(p))) return error(409, 'scripts_not_opened')
      installed.push(body)
      const skill = makeSkill({
        id: `skill-reg-${++counter}`,
        name: preview.name,
        origin: 'registry',
        scope: body.scope as Skill['scope'],
      })
      skills.push(skill)
      return json(201, { skill, renamed_to: null })
    }
    if (path === '/api/skills/updates/check') return json(200, {})
    // --- statistics
    if (path === '/api/skills/stats') {
      const rows = (seed.stats ?? []).filter(
        (r) => !query.get('skill_id') || r.skill_id === query.get('skill_id'),
      )
      return json(200, { rows, total: rows.length })
    }
    if (path === '/api/skills/stats/daily') return json(200, seed.daily ?? [])
    if (path === '/api/skills/stats/runs') return json(200, seed.statsRuns ?? [])
    // --- modes and runs
    match = path.match(/^\/api\/(agents|stages)\/([^/]+)\/skill-modes$/)
    if (match) {
      const store = match[1] === 'agents' ? agentModes : stageModes
      const rows = (store[match[2]] ??= [])
      if (method === 'PUT') {
        for (const [skillId, mode] of Object.entries(
          (body.modes as Record<string, string>) ?? {},
        )) {
          const row = rows.find((r) => r.skill.id === skillId)
          if (row) {
            row.mode = mode as SkillModeRow['mode']
            row.effective = row.mode
            row.set_by = mode === 'auto' ? 'default' : match[1] === 'agents' ? 'agent' : 'stage'
          }
        }
      }
      return json(200, rows)
    }
    match = path.match(/^\/api\/runs\/([^/]+)\/skills$/)
    if (match) return json(200, seed.runSkills?.[match[1]] ?? [])
    // --- a file of any skill (proposed ones are not in the library list)
    match = path.match(/^\/api\/skills\/([^/]+)\/files\/(.+)$/)
    if (match) {
      return new Response(files[`${match[1]}/${match[2]}`] ?? `contenido de ${match[2]}`, {
        status: 200,
      })
    }
    // --- one skill
    match = path.match(/^\/api\/skills\/([^/]+)(?:\/(.*))?$/)
    if (!match) return null
    const skill = find(match[1])
    if (!skill) return error(404, 'skill_not_found')
    const rest = match[2] ?? ''
    if (!rest) {
      if (method === 'GET') return json(200, skill)
      if (method === 'DELETE') {
        skills.splice(skills.indexOf(skill), 1)
        return json(204, null)
      }
      if (method === 'PATCH') {
        Object.assign(skill, body)
        return json(200, skill)
      }
    }
    if (rest === 'versions' && method === 'GET') return json(200, versionsOf(skill.id))
    if (rest === 'versions' && method === 'POST') {
      if (typeof body.description === 'string') skill.description = body.description
      if (typeof body.body === 'string') skill.body = body.body
      newVersion(skill, String(body.note ?? 'cambios'), 'user')
      return json(201, skill)
    }
    if (rest.startsWith('restore/')) {
      newVersion(skill, 'Restaurada', 'restore')
      return json(201, skill)
    }
    if (rest === 'diff') {
      const to = query.get('to') ?? 'current'
      return json(200, {
        from_version: 1,
        to_version: skill.version,
        files: seed.diffs?.[to] ?? seed.diffs?.[skill.id] ?? [],
      })
    }
    if (rest === 'origin') return json(200, seed.origins?.[skill.id] ?? null)
    if (rest.startsWith('files/')) {
      const filePath = rest.slice('files/'.length)
      return new Response(files[`${skill.id}/${filePath}`] ?? `contenido de ${filePath}`, {
        status: 200,
      })
    }
    return null
  }

  return { skills, proposals, settings, accepted, installed, versions, handle }
}

export const skillFile = (path: string, executable = false): SkillFile => ({
  path,
  size: 20,
  executable,
})
