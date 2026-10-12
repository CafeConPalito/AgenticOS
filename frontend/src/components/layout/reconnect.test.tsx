import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { invoke, isTauri } from '@tauri-apps/api/core'
import es from '@/i18n/es.json'
import { getApiBaseUrl } from '@/lib/api'
import { renderApp } from '@/test/render'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn(), isTauri: vi.fn(() => true) }))

/** The desktop shell: `backend_url` answers with the URL, «starting» or a final error. */
function shell(answers: { url?: string; error?: string }) {
  vi.mocked(isTauri).mockReturnValue(true)
  vi.mocked(invoke).mockImplementation(async (command: string) => {
    if (command === 'backend_url') {
      if (answers.url) return answers.url
      throw answers.error ?? 'starting'
    }
    return null
  })
}

function healthAt(...urls: string[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (urls.some((u) => url.startsWith(u)))
      return new Response(JSON.stringify({ status: 'ok', name: 'Agentic OS', version: '1.0.0' }))
    throw new TypeError('Failed to fetch')
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('desktop app: the backend restarts (phase 08)', () => {
  beforeEach(() => vi.mocked(invoke).mockReset())

  it('says it is reconnecting while the shell restarts the backend', async () => {
    const answers: { url?: string; error?: string } = { url: 'http://127.0.0.1:5001' }
    shell(answers)
    healthAt('http://127.0.0.1:5001', 'http://127.0.0.1:5002')
    renderApp('/')
    expect(await screen.findByText('Conectado · v1.0.0')).toBeVisible()

    delete answers.url // the backend died: the shell launches it again
    expect(
      await screen.findByText(es.backend.reconnectingTitle, {}, { timeout: 8000 }),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: es.backend.restart })).not.toBeInTheDocument()

    answers.url = 'http://127.0.0.1:5002' // back, on another port
    expect(await screen.findByText('Conectado · v1.0.0', {}, { timeout: 5000 })).toBeVisible()
    await expect(getApiBaseUrl()).resolves.toBe('http://127.0.0.1:5002')
  }, 20_000)

  it('offers «Reintentar» and «Abrir logs» when the shell gave up', async () => {
    shell({ error: 'backend exited (code Some(1))' })
    healthAt()
    const user = userEvent.setup()
    renderApp('/')

    expect(await screen.findByText(es.backend.failedTitle)).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.backend.openLogs }))
    await user.click(screen.getByRole('button', { name: es.backend.restart }))
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('restart_backend'))
    expect(invoke).toHaveBeenCalledWith('open_logs')
  })
})
