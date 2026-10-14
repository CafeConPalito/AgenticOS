import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { resetApiBaseUrl } from '@/lib/api'
import { Providers } from '@/providers'
import { createFakeBackend, makeRun } from '@/test/fake-backend'
import { type FakeWebSocket, installFakeWebSocket } from '@/test/fake-socket'
import { Terminal } from '@/test/fake-xterm'
import { TerminalPanel } from './TerminalPanel'

vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

async function setup(run = makeRun()) {
  resetApiBaseUrl()
  Terminal.instances = []
  const backend = createFakeBackend({ runs: [run] })
  const Socket = installFakeWebSocket()
  render(
    <Providers>
      <TerminalPanel run={run} />
    </Providers>,
  )
  await waitFor(() => expect(Socket.instances).toHaveLength(1))
  const ws = Socket.instances[0]
  const term = Terminal.instances[0]
  return { backend, ws, term, Socket }
}

function state(ws: FakeWebSocket, controller: string | null) {
  act(() =>
    ws.push({
      type: 'state',
      status: controller ? 'intervening' : 'running',
      activity: 'idle',
      controller,
      cols: 120,
      rows: 32,
    }),
  )
}

describe('TerminalPanel', () => {
  it('connects as a viewer, shows the snapshot and streams output read-only', async () => {
    const { ws, term } = await setup(makeRun({ id: 'run-a' }))
    expect(ws.url).toMatch(/^ws:\/\/.+\/api\/runs\/run-a\/terminal\?client_id=.+/)
    act(() =>
      ws.open(
        { type: 'snapshot', data: 'hola ' },
        {
          type: 'state',
          status: 'running',
          activity: 'busy',
          controller: null,
          cols: 120,
          rows: 32,
        },
      ),
    )
    act(() => ws.push({ type: 'output', data: 'mundo' }))
    expect(term.output).toBe('hola mundo')
    expect(screen.getByText(es.terminal.observing)).toBeVisible()
    expect(screen.getByText('Dev está trabajando…')).toBeVisible()

    term.type('x')
    expect(ws.sent).toEqual([])
  })

  it('take control makes this view interactive; release gives it back', async () => {
    const user = userEvent.setup()
    const { ws, term, backend } = await setup()
    act(() => ws.open({ type: 'snapshot', data: '' }))
    state(ws, null)

    await user.click(screen.getByRole('button', { name: es.terminal.take }))
    expect(backend.callsTo('POST', `/api/runs/${backend.runs[0].id}/control`)[0].body).toEqual({
      action: 'take',
      client_id: ws.viewerId,
    })
    state(ws, ws.viewerId)
    expect(screen.getByText(es.terminal.intervening)).toBeVisible()
    expect(term.options.disableStdin).toBe(false)
    expect(term.focused).toBe(true)

    term.type('ls\r')
    expect(ws.sent).toContainEqual({ type: 'input', data: 'ls\r' })

    await user.click(screen.getByRole('button', { name: es.terminal.release }))
    expect(backend.callsTo('POST', `/api/runs/${backend.runs[0].id}/control`)[1].body).toEqual({
      action: 'release',
      client_id: ws.viewerId,
    })
    state(ws, null)
    expect(screen.getByRole('button', { name: es.terminal.take })).toBeEnabled()
    expect(term.options.disableStdin).toBe(true)
  })

  it('another view holding the control disables «Tomar control»', async () => {
    const { ws } = await setup()
    act(() => ws.open({ type: 'snapshot', data: '' }))
    state(ws, 'other-view')
    expect(screen.getByText(es.terminal.otherController)).toBeVisible()
    expect(screen.getByRole('button', { name: es.terminal.take })).toBeDisabled()
  })

  it('replays a finished run at the sizes recorded in its log', async () => {
    const ESC = String.fromCharCode(27)
    const BEL = String.fromCharCode(7)
    const mark = (cols: number, rows: number) => `${ESC}]7770;size;${cols};${rows}${BEL}`
    const { ws, term } = await setup(makeRun({ status: 'completed', cols: 186, rows: 47 }))
    const sizes: string[] = []
    const resize = term.resize.bind(term)
    term.resize = (cols, rows) => {
      resize(cols, rows)
      sizes.push(`${cols}x${rows}`)
    }
    act(() => ws.open({ type: 'snapshot', data: `${mark(120, 32)}a${mark(186, 47)}b` }))
    expect(term.output).toBe('ab') // the marks never reach the screen
    expect(sizes).toEqual(['120x32', '186x47'])
  })

  it('reconnects after a dropped connection and stops after exit', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const { ws, Socket, term } = await setup()
      act(() => ws.open({ type: 'snapshot', data: 'antes' }))
      act(() => ws.close())
      await act(() => vi.advanceTimersByTimeAsync(300))
      expect(Socket.instances).toHaveLength(2)
      const again = Socket.instances[1]
      expect(again.viewerId).toBe(ws.viewerId)
      act(() => again.open({ type: 'snapshot', data: 'antes y después' }))
      expect(term.output).toBe('antes y después')

      act(() => again.push({ type: 'exit', code: 0, status: 'exited' }))
      act(() => again.close())
      await act(() => vi.advanceTimersByTimeAsync(6000))
      expect(Socket.instances).toHaveLength(2)
      expect(screen.getByText(es.terminal.finished)).toBeVisible()
      expect(screen.queryByRole('button', { name: es.terminal.take })).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})
