import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeRun } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { Terminal } from '@/test/fake-xterm'
import { renderApp } from '@/test/render'
import { DOCK_DEFAULTS, useDock } from './dock-store'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

beforeEach(() => {
  useDock.setState({ ...DOCK_DEFAULTS })
})

const dock = () => screen.queryByRole('complementary', { name: es.dock.label })

describe('TerminalDock', () => {
  it('the header button and Ctrl+` toggle it; the state is remembered', async () => {
    createFakeBackend()
    installFakeWebSocket()
    const user = userEvent.setup()
    renderApp('/agentes')
    const button = await screen.findByRole('button', { name: es.dock.toggle })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(dock()).not.toBeInTheDocument()

    await user.click(button)
    expect(dock()).toBeInTheDocument()
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByText(es.dock.empty)).toBeVisible()
    expect(JSON.parse(localStorage.getItem('agentic-os.dock')!).state.open).toBe(true)

    act(() => {
      fireEvent.keyDown(window, { key: 'º', code: 'Backquote', ctrlKey: true })
    })
    expect(dock()).not.toBeInTheDocument()
    act(() => {
      fireEvent.keyDown(window, { key: 'º', code: 'Backquote', ctrlKey: true })
    })
    expect(dock()).toBeInTheDocument()
  })

  it('shows one tab per active run and streams the selected one, read-only', async () => {
    const first = makeRun({ prompt: 'Primera tarea', agent_name: 'Dev' })
    const second = makeRun({ prompt: 'Segunda tarea', agent_name: 'Rita', activity: 'idle' })
    const finished = makeRun({ prompt: 'Vieja', status: 'exited', exit_code: 0 })
    createFakeBackend({ runs: [first, second, finished] })
    const Socket = installFakeWebSocket()
    useDock.setState({ open: true })
    const user = userEvent.setup()
    const { router } = renderApp('/')

    const tabs = await within(dock()!).findAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(['DPrimera tarea', 'RSegunda tarea'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(Socket.instances.at(-1)?.url).toContain(`/runs/${first.id}/`))
    expect(within(dock()!).getByText(es.terminal.dockReadOnly)).toBeVisible()
    expect(within(dock()!).queryByRole('button', { name: es.terminal.take })).toBeNull()

    // Passive viewer: starts at the PTY size, follows it, never imposes its own.
    const ws = Socket.instances.at(-1)!
    const term = Terminal.instances.at(-1)!
    expect([term.cols, term.rows]).toEqual([first.cols, first.rows])
    act(() => {
      ws.open({ type: 'snapshot', data: '' })
      ws.push({
        type: 'state',
        status: 'running',
        activity: 'busy',
        controller: null,
        cols: 199,
        rows: 49,
      })
    })
    expect([term.cols, term.rows]).toEqual([199, 49])
    expect(ws.sent).toEqual([])

    await user.click(tabs[1])
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(Socket.instances.at(-1)?.url).toContain(`/runs/${second.id}/`))
    expect(Socket.instances.find((s) => s.url.includes(first.id))?.readyState).toBe(Socket.CLOSED)

    await user.click(within(dock()!).getByRole('button', { name: es.dock.expand }))
    expect(router.state.location.pathname).toBe(`/ejecuciones/${second.id}`)
  })

  it('docks to the right and back, and closes', async () => {
    createFakeBackend()
    installFakeWebSocket()
    useDock.setState({ open: true })
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: es.dock.toRight }))
    expect(dock()).toHaveClass('w-[440px]')
    await user.click(screen.getByRole('button', { name: es.dock.toBottom }))
    expect(dock()).toHaveClass('h-[260px]')
    await user.click(screen.getByRole('button', { name: es.dock.close }))
    expect(dock()).not.toBeInTheDocument()
  })
})
