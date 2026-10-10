import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeProject, makeRun } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

beforeEach(() => {
  installFakeWebSocket()
})

describe('Launch a run', () => {
  it('from the agent header: picks the only project and opens the run page', async () => {
    const agent = makeAgent({ name: 'Dev' })
    const project = makeProject({ name: 'Tienda online' })
    const backend = createFakeBackend({ agents: [agent], projects: [project] })
    const user = userEvent.setup()
    const { router } = renderApp(`/agentes/${agent.id}/general`)

    await user.click(await screen.findByRole('button', { name: es.runs.launch.button }))
    const dialog = await screen.findByRole('dialog', { name: es.runs.launch.title })
    const prompt = within(dialog).getByLabelText(es.runs.launch.prompt)
    expect(prompt).toHaveFocus()
    expect(
      within(dialog).getByRole('combobox', { name: es.runs.launch.project }),
    ).toHaveTextContent('Tienda online')
    await user.type(prompt, 'Arregla el checkout')
    await user.click(within(dialog).getByRole('button', { name: es.runs.launch.submit }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/ejecuciones/${backend.runs[0].id}`),
    )
    expect(backend.callsTo('POST', '/api/runs')[0].body).toEqual({
      agent_id: agent.id,
      project_id: project.id,
      prompt: 'Arregla el checkout',
    })
    expect(await screen.findByRole('heading', { name: 'Arregla el checkout' })).toBeVisible()
    expect(screen.getByRole('region', { name: es.terminal.label })).toBeVisible()
    // The agent's edit form must not have been submitted by the dialog.
    expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)).toHaveLength(0)
  })

  it('from the project header with Ctrl+Enter, choosing the agent', async () => {
    const dev = makeAgent({ name: 'Dev' })
    const qa = makeAgent({ name: 'Rita', cli: 'claude' })
    const project = makeProject({ name: 'Blog' })
    const backend = createFakeBackend({ agents: [dev, qa], projects: [project] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/summary`)

    await user.click(await screen.findByRole('button', { name: es.runs.launch.button }))
    const dialog = await screen.findByRole('dialog')
    const submit = within(dialog).getByRole('button', { name: es.runs.launch.submit })
    await user.type(within(dialog).getByLabelText(es.runs.launch.prompt), 'Revisa los tests')
    expect(submit).toBeDisabled() // no agent yet
    await user.click(within(dialog).getByRole('combobox', { name: es.runs.launch.agent }))
    await user.click(await screen.findByRole('option', { name: /Rita/ }))
    await user.click(within(dialog).getByLabelText(es.runs.launch.prompt))
    await user.keyboard('{Control>}{Enter}{/Control}')

    await waitFor(() => expect(backend.callsTo('POST', '/api/runs')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/runs')[0].body).toMatchObject({
      agent_id: qa.id,
      project_id: project.id,
    })
  })

  it('shows the backend error when the CLI is not installed', async () => {
    const agent = makeAgent({ name: 'Gema', cli: 'agy' })
    createFakeBackend({ agents: [agent], projects: [makeProject()] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/general`)

    await user.click(await screen.findByRole('button', { name: es.runs.launch.button }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.runs.launch.prompt), 'Hola')
    await user.click(within(dialog).getByRole('button', { name: es.runs.launch.submit }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(es.errors.cli_not_installed)
  })
})

describe('Run page', () => {
  it('shows the run details and stops it after confirmation', async () => {
    const run = makeRun({ prompt: 'Migra la base de datos\ncon cuidado', agent_name: 'Dev' })
    const backend = createFakeBackend({ runs: [run] })
    const user = userEvent.setup()
    renderApp(`/ejecuciones/${run.id}`)

    expect(await screen.findByRole('heading', { name: 'Migra la base de datos' })).toBeVisible()
    expect(screen.getByText(es.runs.status.busy)).toBeVisible()
    expect(screen.getByText(run.cli_session_id!)).toBeVisible()
    expect(await screen.findByText(`Dev · Migra la base de datos`)).toBeVisible() // breadcrumb

    await user.click(screen.getByRole('button', { name: es.runs.stop.button }))
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: es.runs.stop.confirm }))
    await waitFor(() => expect(backend.callsTo('POST', `/api/runs/${run.id}/stop`)).toHaveLength(1))
    expect(await screen.findByText(es.runs.status.stopped)).toBeVisible()
    expect(screen.queryByRole('button', { name: es.runs.stop.button })).not.toBeInTheDocument()
  })

  it('unknown run shows not found', async () => {
    createFakeBackend()
    renderApp('/ejecuciones/nope')
    expect(await screen.findByText(es.runs.notFound)).toBeVisible()
  })
})

describe('Runs list', () => {
  it('lists runs, filters by active and opens one', async () => {
    const live = makeRun({ prompt: 'En marcha', agent_name: 'Dev' })
    const done = makeRun({
      prompt: 'Ya hecha',
      agent_name: 'Rita',
      status: 'exited',
      exit_code: 0,
      ended_at: new Date().toISOString(),
    })
    const backend = createFakeBackend({ runs: [live, done] })
    const user = userEvent.setup()
    const { router } = renderApp('/ejecuciones')

    expect(await screen.findByRole('row', { name: /En marcha/ })).toBeVisible()
    expect(screen.getByRole('row', { name: /Ya hecha/ })).toBeVisible()
    expect(
      within(screen.getByRole('row', { name: /Ya hecha/ })).getByText(es.runs.status.exited),
    ).toBeVisible()

    await user.click(screen.getByRole('switch', { name: es.runs.filters.activeOnly }))
    await waitFor(() =>
      expect(screen.queryByRole('row', { name: /Ya hecha/ })).not.toBeInTheDocument(),
    )
    expect(router.state.location.search).toBe('?activas=1')
    expect(backend.calls.some((c) => c.path === '/api/runs' && c.query === '?active=true')).toBe(
      true,
    )

    await user.click(screen.getByRole('row', { name: /En marcha/ }))
    expect(router.state.location.pathname).toBe(`/ejecuciones/${live.id}`)
  })

  it('is reachable from the sidebar and offers to launch when empty', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/')
    const nav = await screen.findByRole('navigation', { name: es.nav.main })
    await user.click(within(nav).getByRole('link', { name: es.nav.runs }))
    expect(await screen.findByText(es.runs.emptyTitle)).toBeVisible()
    await user.click(screen.getAllByRole('button', { name: es.header.primary.launchRun })[0])
    expect(await screen.findByRole('dialog', { name: es.runs.launch.title })).toBeVisible()
  })

  it('agent history tab shows only that agent’s runs', async () => {
    const agent = makeAgent({ name: 'Dev' })
    const other = makeAgent({ name: 'Rita' })
    createFakeBackend({
      agents: [agent, other],
      runs: [
        makeRun({ agent_id: agent.id, prompt: 'Del Dev' }),
        makeRun({ agent_id: other.id, prompt: 'De Rita' }),
      ],
    })
    renderApp(`/agentes/${agent.id}/history`)
    expect(await screen.findByRole('row', { name: /Del Dev/ })).toBeVisible()
    expect(screen.queryByRole('row', { name: /De Rita/ })).not.toBeInTheDocument()
  })

  it('agent history tab empty state', async () => {
    const agent = makeAgent()
    createFakeBackend({ agents: [agent] })
    renderApp(`/agentes/${agent.id}/history`)
    expect(await screen.findByText(es.runs.agentHistoryEmpty)).toBeVisible()
  })
})
