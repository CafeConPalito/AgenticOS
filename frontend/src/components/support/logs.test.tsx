import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { flush, pendingClientLog, recordClientLog, resetClientLog } from '@/lib/client-log'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const tauri = vi.hoisted(() => ({
  on: false,
  save: vi.fn<() => Promise<string | null>>(),
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}))
vi.mock('@tauri-apps/api/core', async (original) => ({
  ...(await original<typeof import('@tauri-apps/api/core')>()),
  isTauri: () => tauri.on,
  invoke: (cmd: string, args?: unknown) => tauri.invoke(cmd, args),
}))
vi.mock('@tauri-apps/plugin-dialog', async (original) => ({
  ...(await original<typeof import('@tauri-apps/plugin-dialog')>()),
  save: () => tauri.save(),
}))

const L = es.support.logs

beforeEach(() => {
  resetClientLog()
  // As the desktop shell answers: the backend's URL (the fake backend answers any host).
  tauri.invoke.mockImplementation(async (cmd: string) =>
    cmd === 'backend_url' ? 'http://127.0.0.1:8765' : undefined,
  )
})

afterEach(() => {
  tauri.on = false
  tauri.save.mockReset()
  tauri.invoke.mockReset()
})

async function openFromAbout() {
  const backend = createFakeBackend()
  const user = userEvent.setup()
  renderApp('/acerca-de')
  await user.click(await screen.findByRole('button', { name: L.open }))
  const dialog = await screen.findByRole('dialog', { name: L.title })
  return { backend, user, dialog }
}

describe('Preparar registros para enviar (phase 20, block 8; CA12, CA13)', () => {
  it('says what goes in and what never does', async () => {
    const { dialog } = await openFromAbout()
    expect(await within(dialog).findByText('logs/backend.log')).toBeVisible()
    expect(within(dialog).getByText('logs/desktop.log')).toBeVisible()
    expect(within(dialog).getByText('info.txt')).toBeVisible()
    expect(dialog).toHaveTextContent(/salidas de terminal/)
  })

  it('in the browser, saves to Downloads and leads to the folder and the e-mail', async () => {
    const { backend, user, dialog } = await openFromAbout()
    await user.click(await within(dialog).findByRole('button', { name: L.saveDownloads }))
    expect(
      await within(dialog).findByText('Guardado: agentic-os-registros-20261028-1200.zip'),
    ).toBeVisible()
    expect(backend.callsTo('POST', '/api/support/logs/bundle')[0]?.body).toEqual({})
    expect(within(dialog).getByText('Se han ocultado 4 datos sensibles.')).toBeVisible()

    await user.click(within(dialog).getByRole('button', { name: L.reveal }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/support/logs/reveal')).toHaveLength(1))
    const mail = within(dialog).getByRole('link', { name: L.mail }).getAttribute('href')!
    expect(mail).toMatch(/^mailto:contacto@cafeconpalito\.com\?/)
    expect(decodeURIComponent(mail)).toContain(`${L.attach} agentic-os-registros-20261028-1200.zip`)
  })

  it('in the desktop app, asks where to save and shows it in the folder', async () => {
    tauri.on = true
    tauri.save.mockResolvedValue('E:/Soporte/registros.zip')
    const { backend, user, dialog } = await openFromAbout()
    await user.click(await within(dialog).findByRole('button', { name: L.saveAs }))
    expect(await within(dialog).findByText('Guardado: registros.zip')).toBeVisible()
    expect(backend.callsTo('POST', '/api/support/logs/bundle')[0]?.body).toEqual({
      path: 'E:/Soporte/registros.zip',
    })
    await waitFor(() => expect(backend.callsTo('POST', '/api/support/logs/reveal')).toHaveLength(1))
  })

  it('does nothing when «Guardar como» is cancelled', async () => {
    tauri.on = true
    tauri.save.mockResolvedValue(null)
    const { backend, user, dialog } = await openFromAbout()
    await user.click(await within(dialog).findByRole('button', { name: L.saveAs }))
    await waitFor(() => expect(tauri.save).toHaveBeenCalled())
    expect(backend.callsTo('POST', '/api/support/logs/bundle')).toEqual([])
    expect(within(dialog).getByRole('button', { name: L.saveAs })).toBeEnabled()
  })
})

describe('the interface errors (phase 20, block 8)', () => {
  it('are sent in batches to the backend log, and dropped if it is away', async () => {
    const backend = createFakeBackend()
    for (let i = 0; i < 230; i++) recordClientLog('error', new Error(`boom ${i}`), 'test')
    // A ring of the last 200.
    expect(pendingClientLog()).toHaveLength(200)
    expect(pendingClientLog()[0].message).toBe('Error: boom 30')
    await flush()
    const sent = backend.callsTo('POST', '/api/support/client-log')
    expect(sent).toHaveLength(1)
    expect((sent[0].body as { entries: unknown[] }).entries).toHaveLength(50)
    expect(pendingClientLog()).toHaveLength(150)
    while (pendingClientLog().length) await flush()
    expect(backend.callsTo('POST', '/api/support/client-log')).toHaveLength(4)
  })
})
