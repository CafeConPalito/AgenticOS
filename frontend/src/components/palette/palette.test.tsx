import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { useUiPrefs } from '@/stores/ui-prefs'
import { createFakeBackend, makeAgent, makeProject, makeRun, makeTask } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { fold } from './CommandPalette'

function seed() {
  const dev = makeAgent({ name: 'Dev', role: 'Desarrollador' })
  const qa = makeAgent({ name: 'QA', role: 'Pruebas' })
  const tienda = makeProject({ name: 'Tienda online' })
  const tasks = [
    makeTask({ project_id: tienda.id, agent_id: dev.id, title: 'Diseño del login', number: 12 }),
    makeTask({ project_id: tienda.id, agent_id: qa.id, title: 'Pagos con tarjeta', number: 13 }),
  ]
  tasks[0].code = 'T-12'
  tasks[1].code = 'T-13'
  return { dev, qa, tienda, tasks }
}

async function openPalette(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('navigation', { name: es.nav.main })
  await user.keyboard('{Control>}k{/Control}')
  return screen.findByRole('dialog', { name: es.palette.title })
}

describe('fold', () => {
  it('ignores case and accents', () => {
    expect(fold('  Diseño ')).toBe('diseno')
  })
})

describe('Command palette (Ctrl+K)', () => {
  it('opens with Ctrl+K and closes with Esc, also from a field', async () => {
    const { dev, tienda } = seed()
    createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openPalette(user)
    expect(within(dialog).getByPlaceholderText(es.palette.placeholder)).toHaveFocus()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('the header search opens it', async () => {
    const { dev } = seed()
    createFakeBackend({ agents: [dev] })
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: new RegExp(es.header.search) }))
    expect(await screen.findByRole('dialog', { name: es.palette.title })).toBeVisible()
  })

  it('without a search lists actions, sections and agents', async () => {
    const { dev, qa, tienda } = seed()
    createFakeBackend({ agents: [dev, qa], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openPalette(user)

    for (const heading of [es.palette.groups.actions, es.palette.groups.goto]) {
      expect(await within(dialog).findByText(heading)).toBeVisible()
    }
    expect(await within(dialog).findByText('Dev · Desarrollador')).toBeVisible()
    expect(within(dialog).getByText(es.palette.actions.newTask)).toBeVisible()
    expect(within(dialog).getByText(es.palette.goto.inbox)).toBeVisible()
    // Projects and tasks only appear when searching.
    expect(within(dialog).queryByText('Tienda online')).toBeNull()
  })

  it('finds a project and an agent by name', async () => {
    const { dev, qa, tienda } = seed()
    createFakeBackend({ agents: [dev, qa], projects: [tienda] })
    const user = userEvent.setup()
    const { router } = renderApp('/tablero')
    const dialog = await openPalette(user)
    await user.type(within(dialog).getByPlaceholderText(es.palette.placeholder), 'tienda')
    expect(await within(dialog).findByText('Tienda online')).toBeVisible()
    expect(within(dialog).queryByText('QA · Pruebas')).toBeNull()
    await user.keyboard('{Enter}')
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(new RegExp(`^/proyectos/${tienda.id}`)),
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('finds tasks by title (no accents needed) and by T-n', async () => {
    const { dev, qa, tienda, tasks } = seed()
    createFakeBackend({ agents: [dev, qa], projects: [tienda], tasks })
    const user = userEvent.setup()
    const { router } = renderApp('/tablero')
    const dialog = await openPalette(user)
    const input = within(dialog).getByPlaceholderText(es.palette.placeholder)

    await user.type(input, 'diseno')
    expect(await within(dialog).findByText('T-12 · Diseño del login')).toBeVisible()
    expect(within(dialog).queryByText('T-13 · Pagos con tarjeta')).toBeNull()

    await user.clear(input)
    await user.type(input, 'T-13')
    const item = await within(dialog).findByText('T-13 · Pagos con tarjeta')
    await user.click(item)
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/tablero/tareas/${tasks[1].id}`),
    )
  })

  it('shows «Sin resultados»', async () => {
    const { dev } = seed()
    createFakeBackend({ agents: [dev] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openPalette(user)
    await user.type(within(dialog).getByPlaceholderText(es.palette.placeholder), 'zzzz')
    expect(await within(dialog).findByText(es.palette.empty)).toBeVisible()
  })

  it('moves with the arrows and runs an action with Enter', async () => {
    const { dev } = seed()
    createFakeBackend({ agents: [dev] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openPalette(user)
    await within(dialog).findByText(es.palette.actions.newTask)
    await user.keyboard('{ArrowDown}{ArrowUp}{Enter}')
    // «Nueva tarea» is the first action: its dialog replaces the palette.
    expect(await screen.findByRole('heading', { name: es.tasks.new.title })).toBeVisible()
  })

  it('runs the actions: new agent, new project, shortcuts and theme', async () => {
    const { dev } = seed()
    createFakeBackend({ agents: [dev] })
    const user = userEvent.setup()
    renderApp('/tablero')

    let dialog = await openPalette(user)
    await user.click(await within(dialog).findByText(es.palette.actions.newAgent))
    expect(await screen.findByRole('heading', { name: es.agents.new.title })).toBeVisible()
    await user.keyboard('{Escape}')

    dialog = await openPalette(user)
    await user.click(await within(dialog).findByText(es.palette.actions.shortcuts))
    expect(await screen.findByRole('heading', { name: es.shortcuts.title })).toBeVisible()
    await user.keyboard('{Escape}')

    dialog = await openPalette(user)
    await user.click(await within(dialog).findByText(es.palette.actions.toggleTheme))
    await waitFor(() => expect(document.documentElement).not.toHaveClass('dark'))
  })

  it('pauses and resumes the scheduler', async () => {
    const { dev } = seed()
    const backend = createFakeBackend({ agents: [dev], paused: false })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openPalette(user)
    await user.click(await within(dialog).findByText(es.palette.actions.pauseScheduler))
    await waitFor(() => expect(backend.callsTo('POST', '/api/scheduler/pause')).toHaveLength(1))
  })

  it('Ctrl+K does nothing with the focus in a terminal', async () => {
    const { dev, tienda, tasks } = seed()
    const run = makeRun({ agent_id: dev.id, project_id: tienda.id, task_id: tasks[0].id })
    createFakeBackend({ agents: [dev], projects: [tienda], tasks, runs: [run] })
    const user = userEvent.setup()
    renderApp(`/ejecuciones/${run.id}`)
    await screen.findByRole('navigation', { name: es.nav.main })
    const host = document.createElement('div')
    host.className = 'xterm'
    host.innerHTML = '<textarea aria-label="term"></textarea>'
    document.body.appendChild(host)
    const term = within(host).getByLabelText('term')
    term.focus()
    await user.keyboard('{Control>}k{/Control}')
    expect(screen.queryByRole('dialog', { name: es.palette.title })).toBeNull()
    host.remove()
  })
})

describe('Shortcuts help (?)', () => {
  it('opens with ? and lists the shortcuts', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    renderApp('/tablero')
    await screen.findByRole('navigation', { name: es.nav.main })
    await user.keyboard('?')
    const dialog = await screen.findByRole('dialog', { name: es.shortcuts.title })
    for (const label of [
      es.shortcuts.palette,
      es.shortcuts.newTask,
      es.shortcuts.dock,
      es.shortcuts.close,
    ])
      expect(within(dialog).getByText(label)).toBeVisible()
  })

  it('with single-key shortcuts off, ? and N do nothing but Ctrl+K works', async () => {
    useUiPrefs.setState({ singleKeyShortcuts: false })
    createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    renderApp('/tablero')
    await screen.findByRole('navigation', { name: es.nav.main })
    await user.keyboard('?n')
    expect(screen.queryByRole('dialog')).toBeNull()
    await user.keyboard('{Control>}k{/Control}')
    expect(await screen.findByRole('dialog', { name: es.palette.title })).toBeVisible()
  })

  it('Ctrl+K does not stack over another dialog, but closes the palette', async () => {
    createFakeBackend({ agents: [makeAgent()], projects: [makeProject()] })
    const user = userEvent.setup()
    renderApp('/tablero')
    await screen.findByRole('navigation', { name: es.nav.main })
    await user.keyboard('?')
    await screen.findByRole('dialog', { name: es.shortcuts.title })
    await user.keyboard('{Control>}k{/Control}')
    expect(screen.queryByRole('dialog', { name: es.palette.title })).toBeNull()
    await user.keyboard('{Escape}')
    await user.keyboard('{Control>}k{/Control}')
    await screen.findByRole('dialog', { name: es.palette.title })
    await user.keyboard('{Control>}k{/Control}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: es.palette.title })).toBeNull())
  })

  it('single keys do not act while a menu is open', async () => {
    createFakeBackend({ agents: [makeAgent()], projects: [makeProject()] })
    const user = userEvent.setup()
    renderApp('/tablero')
    await screen.findByRole('navigation', { name: es.nav.main })
    const menu = document.createElement('div')
    menu.setAttribute('role', 'menu')
    document.body.append(menu)
    await user.keyboard('n')
    expect(screen.queryByRole('dialog')).toBeNull()
    menu.remove()
    await user.keyboard('n')
    expect(await screen.findByRole('dialog')).toBeVisible()
  })

  it('single keys do not act while a dialog is open', async () => {
    createFakeBackend({ agents: [makeAgent()], projects: [makeProject()] })
    const user = userEvent.setup()
    renderApp('/tablero')
    await screen.findByRole('navigation', { name: es.nav.main })
    await user.keyboard('?')
    await screen.findByRole('dialog', { name: es.shortcuts.title })
    await user.keyboard('n')
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: es.tasks.new.title })).toBeNull()
  })
})
