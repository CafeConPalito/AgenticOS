import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { SessionRow } from '@/api/types'
import es from '@/i18n/es.json'
import { createFakeBackend, emptyUsage, makeInboxItem } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

const plain = (text: string | null) => (text ?? '').replace(/\u00a0|\u202f/g, ' ')

function session(overrides: Partial<SessionRow>): SessionRow {
  return {
    run_id: 'run-1',
    started_at: '2026-10-08T08:30:00Z',
    ended_at: '2026-10-08T08:43:00Z',
    duration_seconds: 780,
    agent_id: 'agent-1',
    agent_name: 'Ana',
    agent_color: '#F27FB2',
    project_id: 'project-1',
    project_name: 'Tienda online',
    task_id: 'task-1',
    task_code: 'T-1',
    task_title: 'Requisitos del checkout',
    cli: 'claude',
    model: 'claude-sonnet-4-5',
    status: 'completed',
    tokens: 230_300,
    cost_usd: 0.62,
    usage_status: 'final',
    ...overrides,
  }
}

function seededUsage() {
  const usage = emptyUsage()
  usage.summary.kpis = {
    cost_usd: 160.38,
    cost_change: 0.12,
    tokens: 66_080_000,
    cache_ratio: 0.68,
    agent_hours: 83.4,
    sessions: 305,
    success_ratio: 0.94,
  }
  usage.breakdown.rows = [
    {
      id: 'agent-2',
      name: 'Dev',
      color: '#4FD1C5',
      cost_usd: 93.19,
      tokens: 1,
      sessions: 3,
      share: 0.58,
    },
    {
      id: 'agent-1',
      name: 'Ana',
      color: '#F27FB2',
      cost_usd: 35.42,
      tokens: 1,
      sessions: 2,
      share: 0.22,
    },
  ]
  usage.sessions = [
    session({}),
    session({
      run_id: 'run-2',
      agent_name: 'Quique',
      cli: 'agy',
      cost_usd: null,
      tokens: 681_200,
      usage_status: 'partial',
      task_id: null,
      task_code: null,
      task_title: null,
    }),
  ]
  return usage
}

describe('Consumo', () => {
  it('shows the KPIs, the breakdown and the sessions, and sorts and filters', async () => {
    const backend = createFakeBackend({ usage: seededUsage() })
    const user = userEvent.setup()
    renderApp('/consumo')

    expect(await screen.findByText('160,38 $', { normalizer: plain })).toBeVisible()
    expect(screen.getByText('+12 % vs. periodo anterior', { normalizer: plain })).toBeVisible()
    expect(screen.getByText('66,08 M')).toBeVisible()
    expect(screen.getByText('68 % servidos desde caché', { normalizer: plain })).toBeVisible()
    expect(screen.getByText('83,4 h')).toBeVisible()
    expect(screen.getByText('equivale a 10 jornadas')).toBeVisible()
    expect(screen.getByText('94 % terminadas sin error', { normalizer: plain })).toBeVisible()

    const breakdown = screen.getByRole('meter', { name: 'Dev' })
    expect(breakdown).toHaveAttribute('aria-valuenow', '58')

    const table = screen.getByRole('table')
    expect(within(table).getByText('Requisitos del checkout')).toBeVisible()
    expect(within(table).getByText(es.usage.sessions.manual)).toBeVisible()
    expect(within(table).getByText('—')).toBeVisible() // agy: no cost
    expect(within(table).getByText(es.usage.sessions.partial)).toBeVisible()

    await user.click(within(table).getByRole('button', { name: es.usage.sessions.columns.cost }))
    await waitFor(() =>
      expect(
        backend.calls.some(
          (c) => c.path === '/api/usage/sessions' && c.query.includes('sort=cost&dir=desc'),
        ),
      ).toBe(true),
    )
    expect(
      within(screen.getByRole('table'))
        .getByRole('columnheader', { name: es.usage.sessions.columns.cost })
        .getAttribute('aria-sort'),
    ).toBe('descending')

    await user.click(screen.getByRole('tab', { name: es.usage.period['7'] }))
    await waitFor(() =>
      expect(
        backend.calls.some((c) => c.path === '/api/usage/summary' && c.query.includes('from=')),
      ).toBe(true),
    )
    await user.click(screen.getByRole('tab', { name: es.usage.chart.byProject }))
    await waitFor(() =>
      expect(
        backend.calls.some(
          (c) => c.path === '/api/usage/daily' && c.query.includes('group=project'),
        ),
      ).toBe(true),
    )
  })

  it('exports the period as CSV from the header', async () => {
    const backend = createFakeBackend({ usage: seededUsage() })
    const createObjectURL = vi.fn(() => 'blob:x')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }))
    const user = userEvent.setup()
    renderApp('/consumo?periodo=7')
    await user.click(await screen.findByRole('button', { name: es.header.primary.exportCsv }))
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled())
    const csv = backend.calls.find((c) => c.path === '/api/usage/sessions.csv')
    expect(csv?.query).toContain('from=')
  })
})

describe('Consumo de hoy (Dashboard)', () => {
  it('shows today and warns near and over the daily limits', async () => {
    const usage = emptyUsage()
    usage.today = {
      ...usage.today,
      tokens: 3_820_000,
      cache_read_tokens: 2_610_000,
      cost_usd: 6.51,
      agents: [{ id: 'agent-1', name: 'Dev', color: '#4FD1C5', cost_usd: 6.51, tokens: 10 }],
      limits: [
        { ...usage.today.limits[0], limit: 8, used: 6.51, ratio: 0.81, near: true },
        {
          ...usage.today.limits[1],
          limit: 1000,
          used: 1200,
          ratio: 1.2,
          near: true,
          reached: true,
          quota_exhausted: true,
        },
      ],
    }
    createFakeBackend({ usage })
    renderApp('/')
    const card = await screen.findByRole('region', { name: es.usage.today.title })
    expect(await within(card).findByText('3,82 M')).toBeVisible()
    expect(within(card).getByText('2,61 M en caché')).toBeVisible()
    expect(within(card).getAllByText('6,51 $', { normalizer: plain }).length).toBeGreaterThan(0)
    expect(within(card).getByText('Cerca del límite diario de Claude Code')).toBeVisible()
    expect(
      within(card).getByText('Antigravity sin cuota: no se lanzan tareas nuevas'),
    ).toBeVisible()
    expect(within(card).getByRole('link', { name: es.usage.today.detail })).toHaveAttribute(
      'href',
      '/consumo',
    )
  })
})

describe('Límites diarios (Ajustes)', () => {
  it('saves the limits and rejects invalid values', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const claude = await screen.findByLabelText(es.settings.limits.claude, { exact: false })
    await user.type(claude, '25,5')
    const agy = screen.getByLabelText(es.settings.limits.agy, { exact: false })
    await user.type(agy, 'mucho')
    expect(screen.getByRole('alert')).toHaveTextContent(es.settings.limits.invalid)
    expect(screen.getByRole('button', { name: es.settings.limits.save })).toBeDisabled()
    await user.clear(agy)
    await user.type(agy, '2.000.000')
    await user.click(screen.getByRole('button', { name: es.settings.limits.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/usage-limits')[0]?.body).toEqual({
        claude_usd: 25.5,
        agy_tokens: 2_000_000,
      }),
    )
  })
})

describe('Inbox · límites y cuota', () => {
  it('resumes after «Cuota agotada» and explains «Límite diario»', async () => {
    const quota = makeInboxItem({
      kind: 'quota',
      title: 'Antigravity se ha quedado sin cuota',
      detail: 'Quota exhausted · Refreshes in 2h',
      command: 'agy',
      run_id: 'run-1',
      notified_at: '2026-10-12T10:00:00Z',
    })
    const limit = makeInboxItem({
      kind: 'limit',
      title: 'Límite diario de Claude Code alcanzado',
      command: 'claude',
      notified_at: '2026-10-12T10:00:00Z',
    })
    const backend = createFakeBackend({ inbox: [quota, limit] })
    const user = userEvent.setup()
    renderApp('/inbox')
    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.quota}: Antigravity se ha quedado sin cuota`,
    })
    expect(within(card).queryByText('agy')).toBeNull() // the CLI is not shown as a command
    expect(within(card).getByText('Quota exhausted · Refreshes in 2h')).toBeVisible()
    await user.click(within(card).getByRole('button', { name: es.inbox.resume }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/inbox/${quota.id}/resume`)).toHaveLength(1),
    )
    const limitCard = await screen.findByRole('article', {
      name: `${es.inbox.kinds.limit}: Límite diario de Claude Code alcanzado`,
    })
    expect(within(limitCard).getByText(es.inbox.limitHint)).toBeVisible()
    expect(within(limitCard).getByRole('link', { name: es.inbox.openSettings })).toHaveAttribute(
      'href',
      '/ajustes',
    )
  })
})
