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
  makeProject,
  makeRun,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { greetingKey } from './Greeting'

beforeEach(() => {
  useUiPrefs.setState({ snoozedAlerts: [] })
  useDialogs.setState({ newTask: null, newAgent: false, newProject: false })
})

function team() {
  const dev = makeAgent({ name: 'Dev', role: 'Desarrollador' })
  const qa = makeAgent({ name: 'QA', role: 'Pruebas', color: '#F27FB2' })
  const draft = makeAgent({ name: 'Borrador', status: 'draft' })
  const project = makeProject({ name: 'Tienda online' })
  return { dev, qa, draft, project }
}

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
    createFakeBackend({
      agents: [dev],
      projects: [project],
      tasks: [task],
      clis: CLIS.map((cli) => ({ ...cli, installed: true, logged_in: cli.id === 'claude' })),
    })
    renderApp('/')

    const aside = await screen.findByRole('complementary', { name: es.home.summary.label })
    expect(await within(aside).findByText('Tienda online')).toBeVisible()
    expect(within(aside).getByText(`Dev · ${task.title}`)).toBeVisible()
    expect(within(aside).getByText(es.home.summary.cliSession.down)).toBeVisible()
    expect(within(aside).getByRole('link', { name: es.home.summary.manage })).toHaveAttribute(
      'href',
      '/ajustes#clis',
    )
  })

  it('the spend meter turns to the limit and links to Consumo', async () => {
    const usage = emptyUsage()
    usage.today = {
      ...usage.today,
      cost_usd: 1.8,
      limits: usage.today.limits.map((l) =>
        l.cli === 'claude' ? { ...l, limit: 2, used: 1.8, ratio: 0.9, near: true } : l,
      ),
    }
    createFakeBackend({ agents: [makeAgent()], usage })
    renderApp('/')
    const meter = await screen.findByRole('link', { name: es.home.summary.spend })
    expect(meter).toHaveAttribute('href', '/consumo')
    expect(within(meter).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '90')
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
      '/ajustes#clis',
    )
  })

  it('warns about a CLI without a session', async () => {
    createFakeBackend({
      agents: [makeAgent()],
      clis: CLIS.map((cli) => ({ ...cli, installed: true, logged_in: cli.id !== 'agy' })),
    })
    renderApp('/')
    expect(await screen.findByText('Antigravity: sin sesión iniciada')).toBeVisible()
    expect(screen.queryByText('Claude Code: sin sesión iniciada')).toBeNull()
  })

  it('warns at 95 % of the daily limit, before the limit request exists', async () => {
    const usage = emptyUsage()
    usage.today = {
      ...usage.today,
      limits: usage.today.limits.map((l) =>
        l.cli === 'claude' ? { ...l, limit: 10, used: 9.7, ratio: 0.97, near: true } : l,
      ),
    }
    createFakeBackend({ agents: [makeAgent()], usage })
    renderApp('/')
    expect(await screen.findByText(/Claude Code casi sin límite diario · 97/)).toBeVisible()
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
    createFakeBackend({
      agents: [makeAgent()],
      clis: CLIS.map((cli) => ({ ...cli, installed: true, logged_in: cli.id !== 'agy' })),
    })
    const user = userEvent.setup()
    renderApp('/')
    const notice = await screen.findByRole('article', { name: /Antigravity: sin sesión/ })
    await user.click(within(notice).getByRole('button', { name: es.home.alerts.snooze }))
    await waitFor(() => expect(screen.queryByText(/Antigravity: sin sesión/)).toBeNull())
    expect(await screen.findByText(es.home.alerts.snoozed)).toBeVisible()
    expect(useUiPrefs.getState().snoozedAlerts).toEqual(['cli-session-agy'])
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

  it('shows skeletons while loading', () => {
    createFakeBackend()
    const { container } = renderApp('/')
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })
})
