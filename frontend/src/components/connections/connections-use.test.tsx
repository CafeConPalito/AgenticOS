import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makeInboxItem,
  makePipeline,
  makeProject,
  makeRun,
} from '@/test/fake-backend'
import { makeConnection } from '@/test/fake-connections'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const c = es.connections

const brief = (name: string, id = `c-${name}`) => ({
  id,
  name,
  description: '',
  icon: '',
  transport: 'http' as const,
  auth: 'none' as const,
  enabled: true,
})

describe('What an agent, a project, a stage and a run do with connections (phase 18, blocks 10–11)', () => {
  it('shows what an agent receives and takes one away', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'Dev' })],
      connections: {
        connections: [makeConnection({ id: 'c-github', name: 'github' })],
        agent: {
          a1: {
            effective: [
              { connection: brief('github'), level: 'general', tools: 12, tokens: 3400 },
              { connection: brief('tienda-db'), level: 'project', tools: 3, tokens: 700 },
            ],
            excluded: [],
            total_tools: 15,
            total_tokens: 4100,
            excluded_ids: [],
            available: [brief('notas', 'c-notas')],
          },
        },
      },
    })
    const user = userEvent.setup()
    renderApp('/agentes/a1/connections')
    const github = (await screen.findByText('github')).closest('li')!
    expect(
      within(github).getByText(/Todos los agentes · 12 herramientas · ~3400 tokens/),
    ).toBeVisible()
    expect(screen.getByText(/Proyecto · 3 herramientas/)).toBeVisible()
    expect(
      screen.getByText('En total: 15 herramientas, unos 4100 tokens de contexto.'),
    ).toBeVisible()
    await user.click(
      within(github).getByRole('switch', { name: 'Que github llegue a este agente' }),
    )
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/agents/a1/connections')[0]?.body).toEqual({
        excluded: ['c-github'],
      }),
    )
  })

  it('gives an agent another connection', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'Dev' })],
      connections: {
        connections: [makeConnection({ id: 'c-notas', name: 'notas', assignments: [] })],
        agent: {
          a1: {
            effective: [],
            excluded: [],
            total_tools: 0,
            total_tokens: 0,
            excluded_ids: [],
            available: [brief('notas', 'c-notas')],
          },
        },
      },
    })
    const user = userEvent.setup()
    renderApp('/agentes/a1/connections')
    expect(await screen.findByText(c.received.none_agent)).toBeVisible()
    await user.click(screen.getByRole('combobox', { name: c.agentTab.pick }))
    await user.click(await screen.findByRole('option', { name: 'notas' }))
    await user.click(screen.getByRole('button', { name: c.agentTab.give }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/c-notas/assignments')[0]?.body).toEqual({
        scope: 'agent',
        project_id: null,
        agent_id: 'a1',
      }),
    )
  })

  it('shows a project’s connections and gives it an existing one', async () => {
    installFakeWebSocket()
    const project = makeProject({ id: 'p1', name: 'Tienda' })
    const backend = createFakeBackend({
      projects: [project],
      connections: {
        connections: [
          makeConnection({
            id: 'c-db',
            name: 'tienda-db',
            assignments: [{ id: 'x', scope: 'project', project_id: 'p1', agent_id: null }],
          }),
          makeConnection({ id: 'c-gh', name: 'github' }),
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/proyectos/p1/connections')
    expect(await screen.findByRole('button', { name: 'Abrir tienda-db' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Abrir github' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('combobox', { name: c.actions.giveExisting }))
    await user.click(await screen.findByRole('option', { name: 'github' }))
    await user.click(screen.getByRole('button', { name: c.actions.give }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/c-gh/assignments')[0]?.body).toEqual({
        scope: 'project',
        project_id: 'p1',
        agent_id: null,
      }),
    )
  })

  it('takes a connection away in one pipeline stage only', async () => {
    installFakeWebSocket()
    const dev = makeAgent({ id: 'a1', name: 'Dev' })
    const project = makeProject({ id: 'p1', name: 'Tienda' })
    const pipeline = makePipeline(project.id, [
      { id: 's-dev', name: 'Desarrollo', agent_id: dev.id, agent_name: 'Dev' },
      { id: 's-qa', name: 'QA', agent_id: dev.id, agent_name: 'Dev' },
    ])
    const backend = createFakeBackend({
      agents: [dev],
      projects: [project],
      pipelines: { [project.id]: pipeline },
      connections: {
        connections: [],
        stage: {
          's-qa': {
            effective: [
              { connection: brief('tienda-db'), level: 'project', tools: 5, tokens: 900 },
            ],
            excluded: [],
            total_tools: 5,
            total_tokens: 900,
            excluded_ids: [],
            agent_id: 'a1',
          },
        },
      },
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/pipeline`)
    const nav = await screen.findByRole('navigation', { name: es.pipeline.stages })
    await user.click(within(nav).getByRole('button', { name: /QA/ }))
    const section = await screen.findByRole('region', { name: c.stageSection.title })
    await user.click(
      within(section).getByRole('switch', { name: 'Que tienda-db llegue en esta etapa' }),
    )
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/stages/s-qa/connections')[0]?.body).toEqual({
        excluded: ['c-tienda-db'],
      }),
    )
  })

  it('shows on the run page what it was given, why one was not, and its calls', async () => {
    installFakeWebSocket()
    createFakeBackend({
      runs: [makeRun({ id: 'r1', status: 'completed' })],
      connections: {
        run: {
          r1: {
            connections: [
              {
                name: 'github',
                connection_id: 'c1',
                status: 'connected',
                detail: '',
                level: 'general',
                revision: 2,
                calls: 2,
                failed_calls: 1,
                last_call_at: new Date().toISOString(),
              },
              {
                name: 'linear',
                connection_id: 'c2',
                status: 'skipped',
                detail: 'Hay que volver a conectar la cuenta de «linear».',
                level: 'general',
                revision: 1,
                calls: 0,
                failed_calls: 0,
                last_call_at: null,
              },
            ],
            calls: [
              {
                id: 'k1',
                connection: 'github',
                tool: 'create_issue',
                started_at: new Date().toISOString(),
                duration_ms: 420,
                ok: true,
                error: '',
              },
              {
                id: 'k2',
                connection: 'github',
                tool: 'merge_pull',
                started_at: new Date().toISOString(),
                duration_ms: 90,
                ok: false,
                error: 'no permission',
              },
            ],
          },
        },
      },
    })
    renderApp('/ejecuciones/r1')
    const panel = await screen.findByRole('region', { name: c.run.title })
    expect(within(panel).getByText(c.run.status_connected)).toBeVisible()
    expect(within(panel).getByText('2 llamadas · 1 falló')).toBeVisible()
    expect(within(panel).getByText(c.run.status_skipped)).toBeVisible()
    expect(within(panel).getByText(/Hay que volver a conectar la cuenta de «linear»/)).toBeVisible()
    const calls = within(panel).getByRole('list', { name: c.run.callsTitle })
    expect(within(calls).getByText('github/create_issue')).toBeVisible()
    expect(within(calls).getByText('420 ms')).toBeVisible()
    expect(within(calls).getByText('no permission')).toBeVisible()
  })

  it('offers to connect the account again from the Inbox', async () => {
    installFakeWebSocket()
    createFakeBackend({
      inbox: [
        makeInboxItem({
          id: 'i1',
          kind: 'connection',
          title: 'Vuelve a conectar «linear»',
          connection_id: 'c-linear',
        }),
      ],
      connections: {
        connections: [
          makeConnection({
            id: 'c-linear',
            name: 'linear',
            auth: 'oauth',
            headers: {},
            secrets: [],
            oauth: {
              status: 'needs_reauth',
              account_label: '',
              expires_at: null,
              client_pasted: false,
              redirect_uri: '',
            },
          }),
        ],
      },
    })
    const user = userEvent.setup()
    const { router } = renderApp('/inbox')
    const link = await screen.findByRole('link', { name: es.inbox.reconnect })
    expect(link).toHaveAttribute('href', '/conexiones?conexion=c-linear')
    await user.click(link)
    // the connection opens by itself, with its login
    expect(await screen.findByRole('region', { name: c.oauth.title })).toBeVisible()
    expect(router.state.location.pathname).toBe('/conexiones')
    expect(screen.getAllByText(c.oauth.status_needs_reauth).length).toBeGreaterThan(0)
  })
})

describe('The settings of the connections (phase 18)', () => {
  it('shows the timeouts, the registries and the programs, and saves a change', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ connections: { connections: [] } })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const title = await screen.findByRole('heading', { name: c.settings.title })
    const section = title.closest('section')!
    expect(await within(section).findByText(/npx · instalado/)).toBeVisible()
    expect(within(section).getByText(/uvx · no está/)).toBeVisible()
    expect(await within(section).findByRole('switch', { name: 'Smithery' })).toBeChecked()
    const grace = within(section).getByLabelText(c.settings.agyGrace)
    await user.clear(grace)
    await user.type(grace, '9')
    await user.click(within(section).getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/connections')[0]?.body).toMatchObject({
        agy_grace: 9,
      }),
    )
  })
})
