import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { highestWindow, isOver, resetsText, windowName } from '@/lib/quota'
import type { QuotaWindow } from '@/api/types'
import { useDialogs } from '@/stores/dialogs'
import {
  CLIS,
  createFakeBackend,
  emptyUsage,
  makeAccount,
  makeAgent,
  makeProject,
  makeRun,
  makeTask,
  systemAccounts,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

const BOTH = CLIS.map((cli) => ({ ...cli, installed: true }))
const later = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString()

function window(overrides: Partial<QuotaWindow> = {}): QuotaWindow {
  return {
    id: 'five_hour',
    used_pct: 50,
    resets_at: later(120),
    read_at: new Date().toISOString(),
    expired: false,
    ...overrides,
  }
}

describe('lib/quota', () => {
  it('names each window the way its CLI does', () => {
    expect(windowName('five_hour')).toBe('Ventana de 5 h')
    expect(windowName('seven_day')).toBe('Semanal')
    expect(windowName('3p-weekly')).toBe('Claude y GPT · semanal')
    expect(windowName('gemini-5h')).toBe('Gemini · 5 h')
    expect(windowName('nuevo-bucket')).toBe('nuevo-bucket') // unknown ids show as they come
  })

  it('a window past its reset no longer counts, even if the backend has not said so yet', () => {
    const now = Date.now()
    expect(isOver(window({ resets_at: new Date(now - 1000).toISOString() }), now)).toBe(true)
    expect(isOver(window({ expired: true }), now)).toBe(true)
    expect(isOver(window(), now)).toBe(false)
    const account = makeAccount({
      quota: [
        window({ id: 'five_hour', used_pct: 30 }),
        window({ id: 'seven_day', used_pct: 80 }),
        window({ id: 'old', used_pct: 99, resets_at: new Date(now - 1000).toISOString() }),
      ],
    })
    expect(highestWindow(account, now)?.id).toBe('seven_day')
    expect(highestWindow(makeAccount(), now)).toBeUndefined()
  })

  it('says when it resets: minutes within a day, a weekday beyond', () => {
    const now = Date.now()
    expect(resetsText(window({ resets_at: new Date(now + 112 * 60_000).toISOString() }), now)).toBe(
      'Se reinicia en 1 h 52 min',
    )
    expect(resetsText(window({ resets_at: new Date(now + 40 * 60_000).toISOString() }), now)).toBe(
      'Se reinicia en 40 min',
    )
    expect(
      resetsText(window({ resets_at: new Date(now + 3 * 24 * 3600_000).toISOString() }), now),
    ).toMatch(/^Se reinicia el /)
  })
})

describe('Cuenta en Ejecuciones y en la tarea', () => {
  it('the runs table has an «Cuenta» column, muted, with the account each run used', async () => {
    const run = makeRun({
      account_id: 'account-personal',
      account_label: 'marta.personal@gmail.com',
    })
    const old = makeRun({ account_label: '' })
    createFakeBackend({ runs: [run, old] })
    renderApp('/ejecuciones')
    expect(await screen.findByRole('columnheader', { name: es.runs.columns.account })).toBeVisible()
    const rows = await screen.findAllByRole('row')
    expect(within(rows[1]).getByText('marta.personal@gmail.com')).toHaveClass(
      'text-muted-foreground',
    )
    // Columns: inicio, agente, tarea, proyecto, estado, cuenta…
    expect(within(rows[2]).getAllByRole('cell')[5]).toHaveTextContent('—')
  })

  it('the run page lists the account in its details', async () => {
    const run = makeRun({ account_label: 'marta.personal@gmail.com', status: 'completed' })
    createFakeBackend({ runs: [run] })
    renderApp(`/ejecuciones/${run.id}`)
    expect(await screen.findByText(es.runs.details.account)).toBeVisible()
    expect(await screen.findByText('marta.personal@gmail.com')).toBeVisible()
  })

  it('the task shows the account in the line under the live output', async () => {
    const project = makeProject({ name: 'Tienda' })
    const dev = makeAgent({ name: 'Dev' })
    const run = makeRun({
      agent_id: dev.id,
      project_id: project.id,
      account_label: 'marta@estudio.es',
      status: 'completed',
    })
    const task = makeTask({
      agent_id: dev.id,
      project_id: project.id,
      status: 'done',
      active_run_id: null,
      last_run_id: run.id,
    })
    createFakeBackend({ agents: [dev], projects: [project], runs: [run], tasks: [task] })
    renderApp(`/tablero/tareas/${task.id}`)
    const facts = await screen
      .findByRole('group', { name: es.tasks.facts.label })
      .catch(() => screen.findByLabelText(es.tasks.facts.label))
    expect(within(facts).getByText(es.tasks.facts.account)).toBeVisible()
    expect(within(facts).getByText('marta@estudio.es')).toBeVisible()
  })

  it.each([
    ['limit', 'Límite diario de Claude Code alcanzado'],
    ['quota', 'Claude Code sin cuota'],
    ['session', 'Claude Code sin sesión'],
  ] as const)('a queued task held by its account says why: %s', async (blocked, text) => {
    const project = makeProject()
    const dev = makeAgent({ name: 'Dev' })
    const task = makeTask({
      agent_id: dev.id,
      project_id: project.id,
      status: 'queued',
      blocked,
      blocked_by: 'Claude Code',
    })
    createFakeBackend({ agents: [dev], projects: [project], tasks: [task] })
    renderApp('/tablero')
    expect(await screen.findByText(text)).toBeVisible()
  })
})

describe('Consumo por cuenta', () => {
  it('groups by account and filters by one, only once there is something to choose', async () => {
    const [claude, agy] = systemAccounts()
    const second = makeAccount({
      id: 'account-personal',
      cli: 'claude',
      name: 'marta.personal@gmail.com',
    })
    const backend = createFakeBackend({ accounts: [claude, second, agy], usage: emptyUsage() })
    const user = userEvent.setup()
    renderApp('/consumo?agrupar=cuenta')

    const filter = await screen.findByRole('combobox', { name: es.usage.filters.account })
    await waitFor(() =>
      expect(
        backend.calls.some(
          (c) => c.path === '/api/usage/daily' && c.query.includes('group=account'),
        ),
      ).toBe(true),
    )
    expect(
      backend.calls.some(
        (c) => c.path === '/api/usage/breakdown' && c.query.includes('group=account'),
      ),
    ).toBe(true)
    expect(screen.getByText(es.usage.chart.titleAccount)).toBeVisible()

    await user.click(filter)
    await user.click(await screen.findByRole('option', { name: /marta\.personal@gmail\.com/ }))
    await waitFor(() =>
      expect(
        backend.calls.some(
          (c) => c.path === '/api/usage/summary' && c.query.includes('account_id=account-personal'),
        ),
      ).toBe(true),
    )
  })

  it('with only the two system accounts there is no account filter', async () => {
    createFakeBackend({ usage: emptyUsage() })
    renderApp('/consumo')
    await screen.findByRole('heading', { name: es.pages.usage.title })
    expect(screen.queryByRole('combobox', { name: es.usage.filters.account })).toBeNull()
  })
})

describe('Límites diarios por cuenta (Ajustes)', () => {
  it('one limit per account, named by its CLI and account when the CLI has several', async () => {
    const [claude, agy] = systemAccounts()
    const second = makeAccount({
      id: 'account-personal',
      cli: 'claude',
      name: 'marta.personal@gmail.com',
      daily_limit: 8,
    })
    const backend = createFakeBackend({ accounts: [claude, second, agy] })
    const user = userEvent.setup()
    renderApp('/ajustes')

    const system = await screen.findByLabelText(
      'Claude Code · Cuenta del sistema · coste del día',
      {
        exact: false,
      },
    )
    const personal = screen.getByLabelText(
      'Claude Code · marta.personal@gmail.com · coste del día',
      {
        exact: false,
      },
    )
    expect(personal).toHaveValue('8')
    expect(system).toHaveValue('')
    // agy has a single account: just the CLI's name.
    expect(screen.getByLabelText('Antigravity · tokens del día', { exact: false })).toBeVisible()

    await user.type(system, '15')
    await user.clear(personal)
    await user.click(screen.getByRole('button', { name: es.settings.limits.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/usage-limits')).toHaveLength(1),
    )
    expect(backend.callsTo('PUT', '/api/settings/usage-limits')[0].body).toEqual({
      limits: [
        { account_id: claude.id, daily_limit: 15 },
        { account_id: 'account-personal', daily_limit: null },
        { account_id: agy.id, daily_limit: null },
      ],
    })
  })
})

describe('Paleta · cuentas y equipos', () => {
  async function open(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByRole('navigation', { name: es.nav.main })
    await user.keyboard('{Control>}k{/Control}')
    return screen.findByRole('dialog', { name: es.palette.title })
  }

  it('«Nuevo equipo» opens the team dialog and «Añadir cuenta» goes to CLIs y cuentas', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    const { router } = renderApp('/tablero')

    const palette = await open(user)
    await user.type(within(palette).getByRole('combobox'), 'equipo')
    await user.click(
      await within(palette).findByRole('option', { name: es.palette.actions.newTeam }),
    )
    expect(await screen.findByRole('dialog', { name: es.teams.newTitle })).toBeVisible()
    expect(useDialogs.getState().newTeam).toBe('new')
    await user.keyboard('{Escape}')

    const again = await open(user)
    await user.type(within(again).getByRole('combobox'), 'cuenta')
    await user.click(
      await within(again).findByRole('option', { name: es.palette.actions.addAccount }),
    )
    await waitFor(() => expect(router.state.location.pathname).toBe('/clis'))
    expect(
      await screen.findByRole('dialog', { name: 'Añadir cuenta de Claude Code' }),
    ).toBeVisible()
  })

  it('«CLIs y cuentas» is one of the places to go', async () => {
    createFakeBackend({ clis: BOTH })
    const user = userEvent.setup()
    const { router } = renderApp('/tablero')
    const palette = await open(user)
    await user.type(within(palette).getByRole('combobox'), 'cuentas')
    await user.click(await within(palette).findByRole('option', { name: es.palette.goto.clis }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/clis'))
    expect(await screen.findByRole('heading', { name: es.clis.title })).toBeVisible()
  })
})
