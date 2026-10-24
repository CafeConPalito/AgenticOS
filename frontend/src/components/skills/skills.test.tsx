import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeProject } from '@/test/fake-backend'
import { makeSkill, makeVersion } from '@/test/fake-skills'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const s = es.skills

function library() {
  return [
    makeSkill({
      id: 'rev',
      name: 'revision-codigo',
      used: 41,
      last_used: new Date().toISOString(),
    }),
    makeSkill({ id: 'mig', name: 'migraciones', enabled: false, executables: 1, origin: 'agent' }),
  ]
}

describe('The skill library (phase 17, block 7)', () => {
  it('lists the cards with their level, origin and usage, and the active count', async () => {
    installFakeWebSocket()
    createFakeBackend({ skills: { skills: library() } })
    renderApp('/conocimiento?vista=skills')
    const card = (await screen.findByRole('button', { name: 'Abrir revision-codigo' })).closest(
      'article',
    )!
    expect(within(card).getByText(/Usada 41 veces/)).toBeVisible()
    const other = screen.getByRole('button', { name: 'Abrir migraciones' }).closest('article')!
    expect(within(other).getByText(s.origin.agent)).toBeVisible()
    expect(within(other).getByText(/1 ejecutables/)).toBeVisible()
    expect(screen.getByText('1 activas de 2')).toBeVisible()
  })

  it('switches a skill off from its card', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ skills: { skills: library() } })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=skills')
    await user.click(await screen.findByRole('switch', { name: 'Activar revision-codigo' }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/skills/rev')[0]?.body).toEqual({ enabled: false }),
    )
  })

  it('creates a skill with a support file', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ skills: { skills: [] } })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=skills')
    await user.click(await screen.findByRole('button', { name: s.actions.new }))
    await user.type(screen.getByLabelText(s.editor.name), 'notas-de-version')
    await user.type(screen.getByLabelText(s.editor.description), 'Escribe changelogs.')
    await user.type(screen.getByRole('textbox', { name: s.editor.newPath }), 'plantilla.md')
    await user.click(screen.getByRole('button', { name: s.editor.addFile }))
    await user.type(screen.getByLabelText('Contenido de plantilla.md'), 'Novedades')
    await user.click(screen.getByRole('button', { name: s.actions.save }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/skills')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/skills')[0].body).toMatchObject({
      scope: 'general',
      name: 'notas-de-version',
      description: 'Escribe changelogs.',
      files: { 'plantilla.md': { text: 'Novedades' } },
    })
  })

  it('shows the history and restores a version', async () => {
    installFakeWebSocket()
    const skill = makeSkill({ id: 'rev', version: 2, versions: 2 })
    const backend = createFakeBackend({
      skills: {
        skills: [skill],
        versions: {
          rev: [
            makeVersion({ id: 'rev-v2', number: 2, note: '+3 -1 en SKILL.md' }),
            makeVersion({
              id: 'rev-v1',
              number: 1,
              current: false,
              author: { ...makeVersion().author, kind: 'agent', label: 'Dev' },
            }),
          ],
        },
      },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=skills')
    await user.click(await screen.findByRole('button', { name: 'Abrir revision-codigo' }))
    await user.click(await screen.findByRole('tab', { name: s.sheet.tabs.history }))
    const list = await screen.findByRole('list', { name: s.history.title })
    expect(within(list).getByText('+3 -1 en SKILL.md')).toBeVisible()
    expect(within(list).getByText(/Dev \(agente\)/)).toBeVisible()
    await user.click(within(list).getByRole('button', { name: 'Restaurar la versión 1' }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/skills/rev/restore/rev-v1')).toHaveLength(1),
    )
  })

  it('imports the CLIs’ skills, each to the level the person picks', async () => {
    installFakeWebSocket()
    const agent = makeAgent({ id: 'a1', name: 'Dev' })
    const backend = createFakeBackend({
      agents: [agent],
      skills: {
        skills: [],
        cliSkills: [
          {
            source: 'claude_user',
            path: 'C:/u/.claude/skills/mia',
            name: 'mia',
            description: 'Mi revisión',
            project_id: null,
            project_name: '',
            imported: false,
            error: '',
          },
          {
            source: 'agy_global',
            path: 'C:/u/.gemini/config/skills/otra',
            name: 'otra',
            description: 'Otra',
            project_id: null,
            project_name: '',
            imported: true,
            error: '',
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=skills')
    await user.click(await screen.findByRole('button', { name: s.actions.import }))
    await user.click(screen.getByRole('tab', { name: s.import.fromClis }))
    expect(await screen.findByText(s.import.already)).toBeVisible()
    await user.click(screen.getByRole('checkbox', { name: 'Importar mia' }))
    const level = screen.getByRole('group', { name: 'Nivel de mia' })
    await user.click(within(level).getByRole('combobox', { name: s.level.label }))
    await user.click(screen.getByRole('option', { name: s.level.agent }))
    await user.click(screen.getByRole('button', { name: 'Importar 1' }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/skills/cli-import')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/skills/cli-import')[0].body).toEqual({
      items: [
        { path: 'C:/u/.claude/skills/mia', scope: 'agent', project_id: null, agent_id: 'a1' },
      ],
    })
  })
})

describe('Skills in the agents, the stages and the runs (block 8)', () => {
  it('sets a skill to «Siempre» for an agent', async () => {
    installFakeWebSocket()
    const agent = makeAgent({ id: 'a1', name: 'Dev' })
    const skill = makeSkill({ id: 'rev' })
    const backend = createFakeBackend({
      agents: [agent],
      skills: {
        skills: [skill],
        agentModes: { a1: [{ skill, mode: 'auto', effective: 'auto', set_by: 'default' }] },
      },
    })
    const user = userEvent.setup()
    renderApp('/agentes/a1/skills')
    await user.click(await screen.findByRole('combobox', { name: 'Modo de revision-codigo' }))
    await user.click(screen.getByRole('option', { name: s.modes.always }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/agents/a1/skill-modes')[0]?.body).toEqual({
        modes: { rev: 'always' },
      }),
    )
  })

  it('warns an agy agent that its global skills load anyway', async () => {
    installFakeWebSocket()
    createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'Dev', cli: 'agy' })],
      skills: {
        agentModes: { a1: [] },
        cliSkills: [
          {
            source: 'agy_global',
            path: 'x',
            name: 'global',
            description: '',
            project_id: null,
            project_name: '',
            imported: false,
            error: '',
          },
        ],
      },
    })
    renderApp('/agentes/a1/skills')
    expect(await screen.findByRole('note')).toHaveTextContent(
      /agy carga también tus skills globales \(1\)/,
    )
  })

  it('shows in a run which skills it got, how and in which version', async () => {
    installFakeWebSocket()
    const project = makeProject({ id: 'p1' })
    const { makeRun } = await import('@/test/fake-backend')
    const run = makeRun({ id: 'r1', project_id: 'p1' })
    createFakeBackend({
      projects: [project],
      runs: [run],
      skills: {
        runSkills: {
          r1: [
            {
              skill_id: 'rev',
              skill_name: 'revision-codigo',
              offered: 'candidate',
              rank: 1,
              score: 0.86,
              loaded_via: 'tool',
              loaded_at: new Date().toISOString(),
              version: 3,
            },
            {
              skill_id: 'mig',
              skill_name: 'migraciones',
              offered: 'candidate',
              rank: 2,
              score: 0.84,
              loaded_via: null,
              loaded_at: null,
              version: 1,
            },
          ],
        },
      },
    })
    renderApp('/ejecuciones/r1')
    const panel = await screen.findByRole('region', { name: s.run.title })
    expect(await within(panel).findByText(s.run.autoselected)).toBeVisible()
    expect(within(panel).getByText(/con use_skill/)).toBeVisible()
    expect(within(panel).getByText('v3')).toBeVisible()
    expect(within(panel).getByText(s.run.notLoaded)).toBeVisible()
  })
})
