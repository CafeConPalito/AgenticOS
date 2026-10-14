import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { resetApiBaseUrl } from '@/lib/api'
import {
  CLIS,
  createFakeBackend,
  makeAccount,
  makeAgent,
  systemAccounts,
} from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { Terminal } from '@/test/fake-xterm'
import { renderApp } from '@/test/render'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

const BOTH_INSTALLED = CLIS.map((cli) => ({ ...cli, installed: true }))
const later = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString()
const plain = (text: string | null) => (text ?? '').replace(/\u00a0|\u202f/g, ' ')

function twoAccounts() {
  const [claude, agy] = systemAccounts()
  const personal = makeAccount({
    id: 'account-personal',
    cli: 'claude',
    name: 'marta.personal@gmail.com',
    email: 'marta.personal@gmail.com',
    plan: 'pro',
    daily_limit: 10,
    used_today: 2.5,
    quota: [
      {
        id: 'five_hour',
        used_pct: 12,
        resets_at: later(250),
        read_at: new Date().toISOString(),
        expired: false,
      },
      {
        id: 'seven_day',
        used_pct: 86,
        resets_at: later(3 * 24 * 60),
        read_at: new Date().toISOString(),
        expired: false,
      },
    ],
    live_runs: 2,
  })
  return { claude, agy, personal }
}

describe('CLIs y cuentas', () => {
  it('lists each CLI with its accounts, their session and their subscription windows', async () => {
    const { claude, agy, personal } = twoAccounts()
    const dev = makeAgent({ name: 'Dev', account_id: personal.id })
    createFakeBackend({
      agents: [dev],
      clis: BOTH_INSTALLED,
      accounts: [
        claude,
        { ...personal, agents: [{ id: dev.id, name: 'Dev', color: dev.color }] },
        agy,
      ],
    })
    renderApp('/clis')

    expect(await screen.findByRole('heading', { name: es.clis.title })).toBeVisible()
    const claudeSection = await screen.findByRole('region', { name: 'Claude Code' })
    expect(within(claudeSection).getByText('v2.1.296')).toBeVisible()
    const accounts = within(claudeSection).getAllByRole('listitem', { name: /./ })
    expect(accounts.map((a) => a.getAttribute('aria-label'))).toEqual([
      'Cuenta del sistema',
      'marta.personal@gmail.com',
    ])

    const [system, second] = accounts
    expect(within(system).getByText(es.accounts.default)).toBeVisible()
    expect(within(system).getByText(/cuenta del sistema/)).toBeVisible()
    expect(within(system).getByText(es.accounts.quota.none)).toBeVisible()

    expect(within(second).getByText('pro')).toBeVisible()
    expect(within(second).getByText(es.accounts.session.ok)).toBeVisible()
    // The windows, as the CLI's own /usage names them.
    const fiveHour = within(second).getByRole('progressbar', { name: 'Ventana de 5 h' })
    expect(fiveHour).toHaveAttribute('aria-valuenow', '12')
    const weekly = within(second).getByRole('progressbar', { name: 'Semanal' })
    expect(weekly).toHaveAttribute('aria-valuenow', '86')
    expect(within(second).getByText(/Se reinicia en 4 h/)).toBeVisible()
    expect(within(second).getByText(/Se reinicia el/)).toBeVisible()
    // Today's use against its daily limit, and who works with it.
    expect(plain(within(second).getByText(/2,50.*\/.*10,00/).textContent)).toMatch(
      /2,50 \$ \/ 10,00 \$/,
    )
    expect(within(second).getByText('2 sesiones activas')).toBeVisible()
    expect(within(second).getByRole('link', { name: /Dev/ })).toHaveAttribute(
      'href',
      `/agentes/${dev.id}`,
    )
  })

  it('Antigravity has a single account: it says why and offers no «Añadir cuenta»', async () => {
    const [claude, agy] = systemAccounts()
    createFakeBackend({ clis: BOTH_INSTALLED, accounts: [claude, agy] })
    renderApp('/clis')
    const agySection = await screen.findByRole('region', { name: 'Antigravity CLI' })
    expect(within(agySection).getByText(es.clis.single.agy)).toBeVisible()
    expect(within(agySection).queryByRole('button', { name: es.accounts.add.button })).toBeNull()
    const claudeSection = screen.getByRole('region', { name: 'Claude Code' })
    expect(
      within(claudeSection).getByRole('button', { name: es.accounts.add.button }),
    ).toBeVisible()
  })

  it('a CLI that is not installed shows how to install it instead of accounts', async () => {
    createFakeBackend() // the default catalog has agy missing
    renderApp('/clis')
    const agySection = await screen.findByRole('region', { name: 'Antigravity CLI' })
    expect(within(agySection).getByText(es.clis.install.agy)).toBeVisible()
    expect(within(agySection).queryByRole('listitem')).toBeNull()
  })

  it('a logged-out account says so and offers «Reconectar»', async () => {
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      clis: BOTH_INSTALLED,
      accounts: [{ ...claude, session_state: 'down' }, agy],
    })
    renderApp('/clis')
    const section = await screen.findByRole('region', { name: 'Claude Code' })
    const card = within(section).getByRole('listitem', { name: 'Cuenta del sistema' })
    expect(within(card).getByText(es.accounts.session.down)).toBeVisible()
    expect(within(card).getByRole('button', { name: es.accounts.reconnect })).toBeVisible()
  })

  it('«Comprobar» asks the CLIs and every account again', async () => {
    const { claude, agy, personal } = twoAccounts()
    const backend = createFakeBackend({ clis: BOTH_INSTALLED, accounts: [claude, personal, agy] })
    const user = userEvent.setup()
    renderApp('/clis')
    await user.click(await screen.findByRole('button', { name: es.clis.check }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/accounts/${agy.id}/probe`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/accounts/${claude.id}/probe`)).toHaveLength(1)
    expect(backend.callsTo('POST', `/api/accounts/${personal.id}/probe`)).toHaveLength(1)
    expect(backend.calls.some((c) => c.path === '/api/clis' && c.query === '?refresh=true')).toBe(
      true,
    )
    expect(await screen.findByText(es.clis.checked)).toBeVisible()
  })

  it('makes another account the default one', async () => {
    const { claude, agy, personal } = twoAccounts()
    const backend = createFakeBackend({ clis: BOTH_INSTALLED, accounts: [claude, personal, agy] })
    const user = userEvent.setup()
    renderApp('/clis')
    await user.click(
      await screen.findByRole('button', { name: 'Más acciones de marta.personal@gmail.com' }),
    )
    await user.click(await screen.findByRole('menuitem', { name: es.accounts.makeDefault }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/accounts/${personal.id}/default`)).toHaveLength(1),
    )
    expect(backend.accounts.find((a) => a.id === claude.id)?.is_default).toBe(false)
  })

  it('removes an account after confirming, and the system account has no «Quitar»', async () => {
    const { claude, agy, personal } = twoAccounts()
    const backend = createFakeBackend({ clis: BOTH_INSTALLED, accounts: [claude, personal, agy] })
    const user = userEvent.setup()
    renderApp('/clis')

    const claudeSection = await screen.findByRole('region', { name: 'Claude Code' })
    await user.click(
      within(claudeSection).getByRole('button', { name: 'Más acciones de Cuenta del sistema' }),
    )
    expect(screen.queryByRole('menuitem', { name: es.accounts.remove })).toBeNull()
    expect(await screen.findByRole('menuitem', { name: es.accounts.systemKept })).toBeVisible()
    await user.keyboard('{Escape}')

    await user.click(
      screen.getByRole('button', { name: 'Más acciones de marta.personal@gmail.com' }),
    )
    await user.click(await screen.findByRole('menuitem', { name: es.accounts.remove }))
    const confirm = await screen.findByRole('alertdialog')
    expect(within(confirm).getByText(es.accounts.removeDescription)).toBeVisible()
    await user.click(within(confirm).getByRole('button', { name: es.accounts.remove }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', `/api/accounts/${personal.id}`)).toHaveLength(1),
    )
    await waitFor(() =>
      expect(screen.queryByRole('listitem', { name: 'marta.personal@gmail.com' })).toBeNull(),
    )
  })
})

describe('CLIs y cuentas · iniciar sesión', () => {
  async function openLogin(path: string, accounts = systemAccounts()) {
    resetApiBaseUrl()
    Terminal.instances = []
    const backend = createFakeBackend({ clis: BOTH_INSTALLED, accounts })
    const Socket = installFakeWebSocket()
    const rendered = renderApp(path)
    return { backend, Socket, ...rendered }
  }

  it('«Añadir cuenta» creates the account, opens its login and ends with the session checked', async () => {
    const { backend, Socket } = await openLogin('/clis')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: es.clis.addAccount }))
    const add = await screen.findByRole('dialog', { name: 'Añadir cuenta de Claude Code' })
    await user.type(within(add).getByLabelText(es.accounts.add.label), 'Trabajo')
    await user.type(within(add).getByLabelText(es.accounts.add.email), 'marta@estudio.es')
    await user.click(within(add).getByRole('button', { name: es.accounts.add.submit }))

    await waitFor(() => expect(backend.callsTo('POST', '/api/accounts')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/accounts')[0].body).toEqual({
      cli: 'claude',
      label: 'Trabajo',
    })
    const created = backend.accounts.find((a) => a.label === 'Trabajo')!
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/accounts/${created.id}/login`)).toHaveLength(1),
    )
    // The email goes to the login page of the CLI.
    expect(backend.callsTo('POST', `/api/accounts/${created.id}/login`)[0].body).toEqual({
      email: 'marta@estudio.es',
    })

    // Its terminal is the account's login WebSocket.
    const dialog = await screen.findByRole('dialog', { name: 'Iniciar sesión · Claude Code' })
    await waitFor(() => expect(Socket.instances).toHaveLength(1))
    const ws = Socket.instances[0]
    expect(ws.url).toMatch(new RegExp(`/api/accounts/${created.id}/login/terminal\\?client_id=`))
    const term = Terminal.instances[0]
    act(() => ws.open({ type: 'snapshot', data: 'Opening the browser…\r\n' }))
    expect(term.output).toContain('Opening the browser')
    // Whatever is typed goes to the CLI: it may ask for a code.
    term.type('abc123\r')
    expect(ws.sent).toEqual([{ type: 'input', data: 'abc123\r' }])
    expect(within(dialog).getByRole('button', { name: es.accounts.login.cancel })).toBeVisible()

    // The CLI ends: the app asks who is logged in now.
    Object.assign(created, {
      session_state: 'ok',
      email: 'marta@estudio.es',
      name: 'marta@estudio.es',
    })
    act(() => ws.push({ type: 'exit', code: 0, status: 'exited' }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/accounts/${created.id}/probe`)).toHaveLength(1),
    )
    expect(await within(dialog).findByText('Sesión iniciada como marta@estudio.es')).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.accounts.login.close }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('says when the CLI ended without a session, and cancelling stops the login', async () => {
    const { claude } = twoAccounts()
    const [, agy] = systemAccounts()
    const { backend, Socket } = await openLogin('/clis', [
      { ...claude, session_state: 'down' },
      agy,
    ])
    const user = userEvent.setup()
    const section = await screen.findByRole('region', { name: 'Claude Code' })
    const card = within(section).getByRole('listitem', { name: 'Cuenta del sistema' })
    await user.click(within(card).getByRole('button', { name: es.accounts.reconnect }))
    const dialog = await screen.findByRole('dialog', { name: 'Iniciar sesión · Claude Code' })
    await waitFor(() => expect(Socket.instances).toHaveLength(1))
    act(() => Socket.instances[0].open({ type: 'snapshot', data: '' }))

    // Cancelling while it runs asks the backend to stop it.
    await user.click(within(dialog).getByRole('button', { name: es.accounts.login.cancel }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', `/api/accounts/${claude.id}/login`)).toHaveLength(1),
    )
  })

  it('/clis?reconectar=<cuenta> opens that login (a logged-out notice leads here)', async () => {
    const [claude, agy] = systemAccounts()
    const { backend, Socket, router } = await openLogin(`/clis?reconectar=${agy.id}`, [
      { ...claude },
      { ...agy, session_state: 'down' },
    ])
    expect(
      await screen.findByRole('dialog', { name: 'Iniciar sesión · Antigravity' }),
    ).toBeVisible()
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/accounts/${agy.id}/login`)).toHaveLength(1),
    )
    await waitFor(() => expect(Socket.instances).toHaveLength(1))
    expect(Socket.instances[0].url).toContain(`/api/accounts/${agy.id}/login/terminal`)

    // Closing the dialog also drops the query, so a reload does not open it again.
    const user = userEvent.setup()
    act(() => Socket.instances[0].push({ type: 'exit', code: 0, status: 'exited' }))
    await user.click(await screen.findByRole('button', { name: /Cerrar|Cancelar/ }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('/clis?nueva=1 opens «Añadir cuenta» (Ctrl+K and the summary column lead here)', async () => {
    await openLogin('/clis?nueva=1')
    expect(
      await screen.findByRole('dialog', { name: 'Añadir cuenta de Claude Code' }),
    ).toBeVisible()
  })
})

describe('CLIs y cuentas · cuota de Antigravity', () => {
  const agySection = () => screen.findByRole('region', { name: 'Antigravity CLI' })

  it('is an explicit switch that turns the reading on and off', async () => {
    const [claude, agy] = systemAccounts()
    const backend = createFakeBackend({ clis: BOTH_INSTALLED, accounts: [claude, agy] })
    const user = userEvent.setup()
    renderApp('/clis')
    const section = await agySection()
    expect(await within(section).findByText(es.clis.agyQuota.help)).toBeVisible()
    const toggle = within(section).getByRole('switch', { name: es.clis.agyQuota.label })
    expect(toggle).not.toBeChecked()

    await user.click(toggle)
    await waitFor(() => expect(backend.callsTo('PUT', '/api/clis/agy/quota')).toHaveLength(1))
    expect(backend.callsTo('PUT', '/api/clis/agy/quota')[0].body).toEqual({ enabled: true })
    await waitFor(() => expect(toggle).toBeChecked())
    expect(await screen.findByText(es.clis.agyQuota.on)).toBeVisible()

    await user.click(toggle)
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/clis/agy/quota')[1].body).toEqual({ enabled: false }),
    )
    await waitFor(() => expect(toggle).not.toBeChecked())
  })

  it.each([
    ['notAvailable', { available: false }],
    ['taken', { taken: true }],
    ['running', { running: true }],
  ] as const)('is disabled, and says why, when %s', async (reason, state) => {
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      clis: BOTH_INSTALLED,
      accounts: [claude, agy],
      agyQuota: { available: true, enabled: false, taken: false, running: false, ...state },
    })
    renderApp('/clis')
    const section = await agySection()
    expect(await within(section).findByText(es.clis.agyQuota[reason])).toBeVisible()
    expect(within(section).getByRole('switch', { name: es.clis.agyQuota.label })).toBeDisabled()
  })

  it('an own status line of the person can not be switched, but ours can be removed', async () => {
    const [claude, agy] = systemAccounts()
    createFakeBackend({
      clis: BOTH_INSTALLED,
      accounts: [claude, agy],
      agyQuota: { available: true, enabled: true, taken: false, running: false },
    })
    renderApp('/clis')
    const section = await agySection()
    const toggle = await within(section).findByRole('switch', { name: es.clis.agyQuota.label })
    expect(toggle).toBeChecked()
    expect(toggle).toBeEnabled()
  })

  it('shows no switch for Claude Code: its status line is per run, no setting involved', async () => {
    createFakeBackend({ clis: BOTH_INSTALLED })
    renderApp('/clis')
    const claudeSection = await screen.findByRole('region', { name: 'Claude Code' })
    expect(within(claudeSection).queryByRole('switch')).toBeNull()
  })
})
