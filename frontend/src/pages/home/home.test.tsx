import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { useDialogs } from '@/stores/dialogs'
import { useUiPrefs } from '@/stores/ui-prefs'
import {
  CLIS,
  createFakeBackend,
  emptyUsage,
  makeAgent,
  makeInboxItem,
  makeAccount,
  makeProject,
  makeRun,
  makeTask,
  makeTeam,
  systemAccounts,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { greetingKey } from './Greeting'

beforeEach(() => {
  useUiPrefs.setState({ snoozedAlerts: [] })
  useDialogs.setState({ newTask: null, newAgent: false, newProject: false, newTeam: null })
})

function team() {
  const dev = makeAgent({ name: 'Dev', role: 'Desarrollador' })
  const qa = makeAgent({ name: 'QA', role: 'Pruebas', color: '#F27FB2' })
  const draft = makeAgent({ name: 'Borrador', status: 'draft' })
  const project = makeProject({ name: 'Tienda online' })
  return { dev, qa, draft, project }
}

const plain = (text: string | null) => (text ?? '').replace(/\u00a0|\u202f/g, ' ')

/** The agent cards of a region (each one is a div with role=link, with inner links of its own). */
const cardsIn = (region: HTMLElement) =>
  within(region)
    .getAllByRole('link')
    .filter((c) => c.getAttribute('role') === 'link')

describe('Inicio · greeting and summary', () => {
  it('greets by time of day', () => {
    expect(greetingKey(8)).toBe('morning')
    expect(greetingKey(15)).toBe('afternoon')
    expect(greetingKey(22)).toBe('evening')
  })

  it('shows the chips: working, waiting for an answer and spent today', async () => {
    const { dev, qa, project } = team()
    const task = makeTask({ agent_id: dev.id, project_id: project.id, status: 'running' })
    const run = makeRun({ agent_id: dev.id, project_id: project.id, task_id: task.id })
    const usage = emptyUsage()
    usage.today = { ...usage.today, cost_usd: 2.5 }
    createFakeBackend({
      agents: [dev, qa],
      projects: [project],
      tasks: [task],
      runs: [run],
      inbox: [makeInboxItem({ kind: 'blocker', agent_id: qa.id, agent_name: 'QA' })],
      usage,
    })
    renderApp('/')

    expect((await screen.findByText(es.home.chips.working)).textContent).toBe(
      `1${es.home.chips.working}`,
    )
    expect(screen.getByText(es.home.chips.waiting).textContent).toBe(`1${es.home.chips.waiting}`)
    expect(screen.getByText(es.home.chips.spent).textContent?.replaceAll(' ', ' ')).toBe(
      `2,50 $${es.home.chips.spent}`,
    )
    expect(screen.getByText(/1 sesión en vivo/)).toBeVisible()
  })

  it('lists the projects with who works on them and the CLIs with their session', async () => {
    const { dev, project } = team()
    const task = makeTask({ agent_id: dev.id, project_id: project.id, status: 'running' })
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      agents: [dev],
      projects: [project],
      tasks: [task],
      clis: CLIS.map((cli) => ({ ...cli, installed: true, logged_in: cli.id === 'claude' })),
      accounts: [claude, { ...agy, session_state: 'down' }],
    })
    renderApp('/')

    const aside = await screen.findByRole('complementary', { name: es.home.summary.label })
    expect(await within(aside).findByText('Tienda online')).toBeVisible()
    expect(within(aside).getByText(`Dev · ${task.title}`)).toBeVisible()
    expect(await within(aside).findByText(/sin sesión · 1 cuenta/)).toBeVisible()
    expect(within(aside).getByRole('link', { name: es.home.summary.manage })).toHaveAttribute(
      'href',
      '/clis',
    )
  })

  it('shows each CLI with its fullest account and unfolds the accounts', async () => {
    const [claude, agy] = systemAccounts()
    const resets = new Date(Date.now() + 3600_000).toISOString()
    const second = makeAccount({
      id: 'account-personal',
      cli: 'claude',
      name: 'marta.personal@gmail.com',
      plan: 'Pro',
      quota: [
        { id: 'five_hour', used_pct: 82, resets_at: resets, read_at: resets, expired: false },
      ],
      live_runs: 1,
    })
    createFakeBackend({
      agents: [makeAgent()],
      clis: CLIS.map((cli) => ({ ...cli, installed: true })),
      accounts: [
        {
          ...claude,
          quota: [
            { id: 'five_hour', used_pct: 40, resets_at: resets, read_at: resets, expired: false },
          ],
        },
        second,
        agy,
      ],
    })
    const user = userEvent.setup()
    renderApp('/')

    const aside = await screen.findByRole('complementary', { name: es.home.summary.label })
    const row = await within(aside).findByRole('button', { name: 'Ver las cuentas de Claude Code' })
    // The CLI shows its fullest account (82 %), in amber from 80 %.
    expect(within(row).getByText('82 %')).toHaveClass('text-status-waiting')
    expect(within(row).getByText('2 cuentas · 1 sesión')).toBeVisible()
    expect(row).toHaveAttribute('aria-expanded', 'false')

    await user.click(row)
    const accounts = within(aside).getByRole('list', { name: 'Cuentas de Claude Code' })
    const [system, personal] = within(accounts).getAllByRole('listitem')
    expect(within(system).getByText('Cuenta del sistema')).toBeVisible()
    expect(within(system).getByText('40 %')).toBeVisible()
    expect(within(personal).getByText('marta.personal@gmail.com')).toBeVisible()
    expect(within(personal).getByText('82 %')).toBeVisible()
    expect(within(personal).getByText('Pro · 1 sesión')).toBeVisible()
    expect(plain(personal.getAttribute('title'))).toBe('Ventana de 5 h: 82 %')
    expect(row).toHaveAttribute('aria-expanded', 'true')
  })

  it('an expired window no longer counts: the bar falls back to the daily limit', async () => {
    const [claude, agy] = systemAccounts()
    const past = new Date(Date.now() - 3600_000).toISOString()
    createFakeBackend({
      agents: [makeAgent()],
      clis: CLIS.map((cli) => ({ ...cli, installed: true })),
      accounts: [
        {
          ...claude,
          daily_limit: 10,
          used_today: 3,
          quota: [
            { id: 'five_hour', used_pct: 96, resets_at: past, read_at: past, expired: false },
          ],
        },
        agy,
      ],
    })
    renderApp('/')
    const aside = await screen.findByRole('complementary', { name: es.home.summary.label })
    const row = await within(aside).findByRole('button', { name: 'Ver las cuentas de Claude Code' })
    expect(within(row).getByText('30 %')).toBeVisible()
  })

  it('the spend meter turns to the limit and links to Consumo', async () => {
    const usage = emptyUsage()
    usage.today = { ...usage.today, cost_usd: 1.8 }
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      agents: [makeAgent()],
      usage,
      accounts: [{ ...claude, daily_limit: 2, used_today: 1.8 }, agy],
    })
    renderApp('/')
    const meter = await screen.findByRole('link', { name: es.home.summary.spend })
    expect(meter).toHaveAttribute('href', '/consumo')
    expect(await within(meter).findByRole('progressbar')).toHaveAttribute('aria-valuenow', '90')
  })

  it("the day's limit is what the Claude accounts add up to", async () => {
    const usage = emptyUsage()
    usage.today = { ...usage.today, cost_usd: 5 }
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      agents: [makeAgent()],
      usage,
      accounts: [
        { ...claude, daily_limit: 10 },
        makeAccount({ cli: 'claude', name: 'Personal', daily_limit: 10 }),
        { ...agy, daily_limit: 1_000_000, unit: 'tokens' }, // another CLI's unit: not added
      ],
    })
    renderApp('/')
    const meter = await screen.findByRole('link', { name: es.home.summary.spend })
    expect(await within(meter).findByRole('progressbar')).toHaveAttribute('aria-valuenow', '25')
  })
})

describe('Inicio · «Te necesitan»', () => {
  it('orders the requests, shows three and expands the rest in place', async () => {
    const { dev } = team()
    const make = (
      kind: 'approval' | 'question' | 'blocker' | 'attention' | 'review',
      title: string,
    ) => makeInboxItem({ kind, title, agent_id: dev.id })
    createFakeBackend({
      agents: [dev],
      inbox: [
        make('review', 'Revisión R'),
        make('blocker', 'Bloqueo B'),
        make('question', 'Pregunta Q'),
        make('attention', 'Atención A'),
        make('approval', 'Aprobación P'),
      ],
    })
    const user = userEvent.setup()
    renderApp('/')

    const panel = await screen.findByRole('region', { name: es.home.needs.title })
    const articles = () => within(panel).getAllByRole('article')
    await waitFor(() => expect(articles()).toHaveLength(3))
    expect(articles().map((a) => a.getAttribute('aria-label'))).toEqual([
      `${es.inbox.kinds.approval}: ${es.inbox.approvalTitle}`,
      `${es.inbox.kinds.question}: Pregunta Q`,
      `${es.inbox.kinds.blocker}: Bloqueo B`,
    ])

    await user.click(within(panel).getByRole('button', { name: 'Ver todas · 5' }))
    expect(articles()).toHaveLength(5)
    await user.click(within(panel).getByRole('button', { name: es.home.needs.less }))
    expect(articles()).toHaveLength(3)
    expect(within(panel).getByRole('link', { name: es.home.needs.resolved })).toHaveAttribute(
      'href',
      '/inbox?status=resolved',
    )
  })

  it('says nothing is pending when there are no requests', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    renderApp('/')
    expect(await screen.findByText(es.home.needs.empty)).toBeVisible()
    expect(screen.queryByRole('region', { name: es.home.needs.title })).toBeNull()
  })

  it('approves and answers from the panel with the same endpoints as the Inbox', async () => {
    const { dev } = team()
    const approval = makeInboxItem({
      kind: 'approval',
      command: 'npm test',
      agent_id: dev.id,
      run_id: 'run-1',
    })
    const question = makeInboxItem({ kind: 'question', title: '¿Qué base?', options: ['SQLite'] })
    const backend = createFakeBackend({ agents: [dev], inbox: [approval, question] })
    const user = userEvent.setup()
    renderApp('/')

    const panel = await screen.findByRole('region', { name: es.home.needs.title })
    expect(await within(panel).findByText('npm test')).toBeVisible()
    await user.click(within(panel).getByRole('button', { name: es.inbox.approve }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${approval.id}/approve`)).toHaveLength(1),
    )

    const card = within(panel).getByRole('article', { name: /¿Qué base\?/ })
    await user.click(within(card).getByRole('button', { name: 'SQLite' }))
    await user.click(within(card).getByRole('button', { name: es.inbox.answer }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${question.id}/answer`)).toHaveLength(1),
    )
  })

  it('highlights the card of the agent whose request is hovered', async () => {
    const { dev, qa } = team()
    createFakeBackend({
      agents: [dev, qa],
      inbox: [makeInboxItem({ kind: 'question', agent_id: qa.id, agent_name: 'QA' })],
    })
    const user = userEvent.setup()
    renderApp('/')
    const request = await screen.findByRole('article', { name: /Pregunta/ })
    const card = screen.getByRole('link', { name: /^QA, Pruebas/ })
    await user.hover(request)
    expect(card.className).toContain('border-status-waiting')
    await user.unhover(request)
    expect(card.className).not.toContain('border-status-waiting ')
  })
})

describe('Inicio · CLI notices', () => {
  it('asks to install a CLI when none is detected', async () => {
    createFakeBackend({
      agents: [makeAgent()],
      clis: CLIS.map((cli) => ({ ...cli, installed: false, path: null })),
    })
    renderApp('/')
    expect(await screen.findByText(es.cliReadiness.missingTitle)).toBeVisible()
    expect(screen.getByRole('link', { name: es.home.alerts.review })).toHaveAttribute(
      'href',
      '/clis',
    )
  })

  it('a logged-out account asks to reconnect it, from its own request', async () => {
    const [, agy] = systemAccounts()
    const down = makeInboxItem({
      kind: 'account',
      title: 'La sesión de Antigravity está cerrada',
      detail: 'Los agentes que usan esta cuenta no arrancarán tareas.',
      command: agy.id,
    })
    createFakeBackend({ agents: [makeAgent()], inbox: [down] })
    renderApp('/')
    // A system notice: its article carries the title alone.
    const notice = await screen.findByRole('article', {
      name: 'La sesión de Antigravity está cerrada',
    })
    expect(within(notice).getByText(es.home.alerts.kind)).toBeVisible()
    expect(within(notice).getByRole('link', { name: es.inbox.reconnect })).toHaveAttribute(
      'href',
      `/clis?reconectar=${agy.id}`,
    )
    // «Reconectar» says it already: no second «Revisar cuentas» next to it.
    expect(within(notice).queryByRole('link', { name: es.home.alerts.review })).toBeNull()
    expect(within(notice).getByRole('button', { name: es.home.alerts.snooze })).toBeVisible()
  })

  it('warns at 95 % of the daily limit, before the limit request exists', async () => {
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      agents: [makeAgent()],
      accounts: [{ ...claude, daily_limit: 10, used_today: 9.7 }, agy],
    })
    renderApp('/')
    expect(await screen.findByText(/Claude Code casi sin límite diario · 97/)).toBeVisible()
  })

  it('warns when a subscription window is at 95 % or more, and drops it once it has reset', async () => {
    const [claude, agy] = systemAccounts()
    const soon = new Date(Date.now() + 70 * 60_000).toISOString()
    const backend = createFakeBackend({
      agents: [makeAgent()],
      accounts: [
        {
          ...claude,
          quota: [
            { id: 'five_hour', used_pct: 96, resets_at: soon, read_at: soon, expired: false },
            { id: 'seven_day', used_pct: 50, resets_at: soon, read_at: soon, expired: false },
          ],
        },
        agy,
      ],
    })
    renderApp('/')
    const notice = await screen.findByRole('article', {
      name: /Claude Code · Ventana de 5 h al 96 %/,
    })
    expect(within(notice).getByText(/Se reinicia en 1 h 1\d min/)).toBeVisible()
    expect(within(notice).getByRole('link', { name: es.home.alerts.review })).toHaveAttribute(
      'href',
      '/clis',
    )
    // At 90 % there is nothing to say yet.
    backend.accounts[0].quota[0].used_pct = 90
    await waitFor(() => expect(screen.queryByText(/Ventana de 5 h al/)).toBeNull(), {
      timeout: 6000,
    })
  })

  it('paints a quota request as a system notice that keeps its action', async () => {
    const quota = makeInboxItem({
      kind: 'quota',
      title: 'Claude Code: cuota agotada',
      detail: 'Vuelve a las 18:00',
      run_id: 'run-9',
    })
    const backend = createFakeBackend({ agents: [makeAgent()], inbox: [quota] })
    const user = userEvent.setup()
    renderApp('/')

    const notice = await screen.findByRole('article', { name: 'Claude Code: cuota agotada' })
    expect(within(notice).getByText(es.home.alerts.kind)).toBeVisible()
    await user.click(within(notice).getByRole('button', { name: es.inbox.resume }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${quota.id}/resume`)).toHaveLength(1),
    )
  })

  it('«Posponer» hides the notice for the session', async () => {
    const [claude, agy] = systemAccounts()
    const soon = new Date(Date.now() + 3600_000).toISOString()
    createFakeBackend({
      agents: [makeAgent()],
      accounts: [
        {
          ...claude,
          quota: [
            { id: 'five_hour', used_pct: 97, resets_at: soon, read_at: soon, expired: false },
          ],
        },
        agy,
      ],
    })
    const user = userEvent.setup()
    renderApp('/')
    const notice = await screen.findByRole('article', { name: /Ventana de 5 h al 97 %/ })
    await user.click(within(notice).getByRole('button', { name: es.home.alerts.snooze }))
    await waitFor(() => expect(screen.queryByText(/Ventana de 5 h al 97 %/)).toBeNull())
    expect(await screen.findByText(es.home.alerts.snoozed)).toBeVisible()
    expect(useUiPrefs.getState().snoozedAlerts).toEqual([`quota-near-${claude.id}`])
  })
})

describe('Inicio · agents', () => {
  it('shows each agent with its state, sessions and queue; drafts go last', async () => {
    const { dev, qa, draft, project } = team()
    const running = makeTask({ agent_id: dev.id, project_id: project.id, status: 'running' })
    const queued = makeTask({ agent_id: dev.id, project_id: project.id, status: 'queued' })
    const run = makeRun({
      agent_id: dev.id,
      project_id: project.id,
      task_id: running.id,
      task_code: running.code,
    })
    createFakeBackend({
      agents: [draft, dev, qa],
      projects: [project],
      tasks: [running, queued],
      runs: [run],
    })
    renderApp('/')

    const grid = await screen.findByRole('region', { name: es.home.agents.title })
    await within(grid).findByRole('link', { name: /^Dev, Desarrollador/ })
    const cards = within(grid)
      .getAllByRole('link')
      .filter((c) => c.getAttribute('role') === 'link')
    const names = cards.map((c) => c.getAttribute('aria-label')?.split(',')[0])
    expect(names).toEqual(['Dev', 'QA', 'Borrador'])

    const devCard = within(grid).getByRole('link', { name: /^Dev, Desarrollador/ })
    expect(within(devCard).getByText(es.home.agents.states.running)).toBeVisible()
    expect(within(devCard).getByText(running.title)).toBeVisible()
    expect(within(devCard).getAllByText('1 en cola').length).toBeGreaterThan(0)
    const qaCard = within(grid).getByRole('link', { name: /^QA, Pruebas/ })
    expect(within(qaCard).getByText(es.home.agents.free)).toBeVisible()
    const draftCard = within(grid).getByRole('link', { name: /^Borrador/ })
    expect(within(draftCard).getByText(es.home.agents.draft)).toBeVisible()
  })

  it('a pending request marks the card with its badge and the waiting state', async () => {
    const { dev } = team()
    createFakeBackend({
      agents: [dev],
      inbox: [makeInboxItem({ kind: 'question', agent_id: dev.id })],
    })
    renderApp('/')
    const card = await screen.findByRole('link', { name: /^Dev, Desarrollador/ })
    expect(await within(card).findByText('1 petición')).toBeVisible()
    expect(within(card).getByText(es.home.agents.states.waiting)).toBeVisible()
  })

  it('opens the agent on click and the assign dialog from the «+»', async () => {
    const { dev } = team()
    createFakeBackend({ agents: [dev] })
    // The «+» only shows on hover/focus, through CSS that the test does not load.
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    const { router } = renderApp('/')

    const card = await screen.findByRole('link', { name: /^Dev, Desarrollador/ })
    await user.click(within(card).getByRole('button', { name: 'Asignar tarea a Dev' }))
    expect(useDialogs.getState().newTask).toEqual({ agentId: dev.id })
    expect(router.state.location.pathname).toBe('/')

    await user.click(card)
    expect(router.state.location.pathname).toMatch(new RegExp(`^/agentes/${dev.id}`))
  })

  it('the card opens with Enter', async () => {
    const { dev } = team()
    createFakeBackend({ agents: [dev] })
    const user = userEvent.setup()
    const { router } = renderApp('/')
    const card = await screen.findByRole('link', { name: /^Dev, Desarrollador/ })
    card.focus()
    await user.keyboard('{Enter}')
    expect(router.state.location.pathname).toMatch(new RegExp(`^/agentes/${dev.id}`))
  })

  it('offers the first agent when there are none', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/')
    expect(await screen.findByText(es.home.agents.empty.title)).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.home.agents.new }))
    expect(useDialogs.getState().newAgent).toBe(true)
  })

  it('one «Nuevo» holds the new agent, the Architect and the new team (phase 20)', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    const { router } = renderApp('/')
    await user.click(await screen.findByRole('button', { name: es.home.agents.newMenu }))
    expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toEqual([
      es.home.agents.new,
      es.agents.architect,
      es.teams.new,
    ])
    await user.click(screen.getByRole('menuitem', { name: es.home.agents.new }))
    expect(useDialogs.getState().newAgent).toBe(true)
    useDialogs.setState({ newAgent: false })
    // The dialog that just closed hid the page from the accessibility tree until it unmounts.
    await user.click(await screen.findByRole('button', { name: es.home.agents.newMenu }))
    await user.click(await screen.findByRole('menuitem', { name: es.agents.architect }))
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/agentes\/arquitecto\//))
  })

  it('shows skeletons while loading', () => {
    createFakeBackend()
    const { container } = renderApp('/')
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })
})

describe('Inicio · equipos', () => {
  function crew() {
    const ana = makeAgent({ name: 'Ana', role: 'Analista' })
    const dev = makeAgent({ name: 'Dev', role: 'Desarrollador' })
    const qa = makeAgent({ name: 'QA', role: 'Pruebas' })
    const product = makeTeam({ name: 'Producto', agent_ids: [ana.id, dev.id] })
    ana.team_id = product.id
    dev.team_id = product.id
    return { ana, dev, qa, product }
  }

  it('groups the agents by team and keeps the rest under «Sin equipo»', async () => {
    const { ana, dev, qa, product } = crew()
    createFakeBackend({ agents: [ana, dev, qa], teams: [product] })
    renderApp('/')

    const team = await screen.findByRole('region', { name: 'Producto' })
    expect(within(team).getByText('2 agentes · 0 activos')).toBeVisible()
    expect(cardsIn(team).map((c) => c.getAttribute('aria-label')?.split(',')[0])).toEqual([
      'Ana',
      'Dev',
    ])
    const loose = screen.getByRole('region', { name: es.teams.none })
    expect(cardsIn(loose)).toHaveLength(1)
    expect(within(loose).getByRole('link', { name: /^QA, Pruebas/ })).toBeVisible()
    expect(screen.getByText('1 equipos · 3 agentes')).toBeVisible()
  })

  it('shows the single grid again when there are no teams', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    renderApp('/')
    await screen.findByRole('link', { name: /^Dev, Desarrollador/ })
    expect(screen.queryByRole('region', { name: es.teams.none })).toBeNull()
  })

  it('«Nuevo equipo» creates a team with the agents ticked', async () => {
    const { ana, dev, qa, product } = crew()
    const backend = createFakeBackend({ agents: [ana, dev, qa], teams: [product] })
    const user = userEvent.setup()
    renderApp('/')

    // Phase 20: under the single «Nuevo» of the Agents section.
    await user.click(await screen.findByRole('button', { name: es.home.agents.newMenu }))
    await user.click(await screen.findByRole('menuitem', { name: es.teams.new }))
    const dialog = await screen.findByRole('dialog', { name: es.teams.newTitle })
    await user.type(within(dialog).getByLabelText(es.teams.name), 'Contenidos')
    // Ticking an agent of another team says it moves.
    await user.click(within(dialog).getByRole('checkbox', { name: /Dev/ }))
    expect(within(dialog).getByText('pasa de Producto')).toBeVisible()
    await user.click(within(dialog).getByRole('checkbox', { name: /QA/ }))
    await user.click(within(dialog).getByRole('button', { name: es.teams.create }))

    await waitFor(() => expect(backend.callsTo('POST', '/api/teams')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/teams')[0].body).toEqual({
      name: 'Contenidos',
      description: '',
      agent_ids: [dev.id, qa.id],
    })
    // Dev left Producto for the new team.
    const contenidos = await screen.findByRole('region', { name: 'Contenidos' })
    expect(cardsIn(contenidos)).toHaveLength(2)
    expect(cardsIn(screen.getByRole('region', { name: 'Producto' }))).toHaveLength(1)
  })

  it('edits a team from its pencil and deletes it leaving its agents', async () => {
    const { ana, dev, qa, product } = crew()
    const backend = createFakeBackend({ agents: [ana, dev, qa], teams: [product] })
    const user = userEvent.setup()
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Editar el equipo Producto' }))
    const dialog = await screen.findByRole('dialog', { name: es.teams.editTitle })
    const name = within(dialog).getByLabelText(es.teams.name)
    expect(name).toHaveValue('Producto')
    await user.clear(name)
    await user.type(name, 'Producto 2')
    await user.click(within(dialog).getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/teams/${product.id}`)).toHaveLength(1),
    )
    expect(backend.callsTo('PATCH', `/api/teams/${product.id}`)[0].body).toMatchObject({
      name: 'Producto 2',
      agent_ids: [ana.id, dev.id],
    })

    await user.click(await screen.findByRole('button', { name: 'Editar el equipo Producto 2' }))
    const again = await screen.findByRole('dialog', { name: es.teams.editTitle })
    await user.click(within(again).getByRole('button', { name: es.teams.delete }))
    const confirm = await screen.findByRole('alertdialog')
    await user.click(within(confirm).getByRole('button', { name: es.teams.delete }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', `/api/teams/${product.id}`)).toHaveLength(1),
    )
    // The agents stay, in the single grid again.
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Producto 2' })).toBeNull())
    expect(await screen.findAllByRole('link', { name: /^(Ana|Dev|QA),/ })).toHaveLength(3)
  })

  it('«+ Agente» of a team opens «Nuevo agente» with that team chosen', async () => {
    const { ana, dev, qa, product } = crew()
    createFakeBackend({ agents: [ana, dev, qa], teams: [product] })
    const user = userEvent.setup()
    renderApp('/')
    await user.click(
      await screen.findByRole('button', { name: 'Añadir un agente al equipo Producto' }),
    )
    expect(useDialogs.getState().newAgent).toBe(true)
    expect(useDialogs.getState().newAgentInit).toEqual({ teamId: product.id })
    const dialog = await screen.findByRole('dialog', { name: es.agents.new.title })
    expect(within(dialog).getByRole('combobox', { name: es.agents.fields.team })).toHaveTextContent(
      'Producto',
    )
  })
})
