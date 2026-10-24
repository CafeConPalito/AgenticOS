import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { StatsRow } from '@/api/skills'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const st = es.skills.stats

const row = (overrides: Partial<StatsRow> = {}): StatsRow => ({
  skill_id: 'rev',
  name: 'revision-codigo',
  scope: 'general',
  origin: 'user',
  group_key: null,
  group_label: '',
  offered: 10,
  loaded: 8,
  rate: 0.8,
  runs: 8,
  tasks: 6,
  done: 7,
  failed: 1,
  approved: 3,
  rejected: 1,
  avg_cost: 0.12,
  avg_tokens: 1500,
  last_used: new Date().toISOString(),
  via_context: 2,
  via_tool: 5,
  via_native: 1,
  ...overrides,
})

describe('The usage view of the skills (CA20)', () => {
  it('shows the figures, sorts, groups, opens the runs behind a figure and exports', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      skills: {
        stats: [
          row(),
          row({ skill_id: 'mig', name: 'migraciones', loaded: 2, rate: 0.2, done: 2, failed: 0 }),
        ],
        statsRuns: [
          {
            run_id: 'r1',
            started_at: new Date().toISOString(),
            skill_id: 'rev',
            skill_name: 'revision-codigo',
            version: 2,
            offered: 'candidate',
            loaded_via: 'tool',
            agent_name: 'Dev',
            project_name: 'Web',
            stage_name: 'QA',
            pipeline_name: 'Web',
            cli: 'claude',
            model: 'sonnet',
            account_label: 'Personal',
            status: 'completed',
            verdict: null,
            cost_usd: 0.1,
            task_id: null,
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=uso')
    const table = await screen.findByRole('table')
    expect(within(table).getByText('80 %')).toBeVisible()
    expect(
      within(table).getByText(/7 bien · 1 fallidas · 3 aprobadas · 1 rechazadas/),
    ).toBeVisible()
    expect(screen.getByTestId('top-chart')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: st.export })).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Ordenar por Tasa' }))
    await waitFor(() =>
      expect(
        backend.calls.some((c) => c.path === '/api/skills/stats' && c.query.includes('sort=rate')),
      ).toBe(true),
    )
    await user.click(screen.getByRole('combobox', { name: st.groupBy }))
    await user.click(screen.getByRole('option', { name: 'Agrupar por: CLI' }))
    await waitFor(() =>
      expect(
        backend.calls.some(
          (c) => c.path === '/api/skills/stats' && c.query.includes('group_by=cli'),
        ),
      ).toBe(true),
    )
    await user.click(
      screen.getAllByRole('button', { name: 'Ver las ejecuciones de revision-codigo' })[0],
    )
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByRole('link', { name: 'Dev · Web' })).toHaveAttribute(
      'href',
      '/ejecuciones/r1',
    )
  })

  it('keeps the filters in the address', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ skills: { stats: [row()] } })
    renderApp('/conocimiento?vista=uso&u_cli=agy&u_period=7d')
    await screen.findByRole('table')
    const call = backend.calls.find(
      (c) => c.path === '/api/skills/stats' && c.query.includes('cli=agy'),
    )
    expect(call?.query).toMatch(/from=\d{4}-\d{2}-\d{2}/)
  })
})
