import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

describe('Settings · CLIs detectados', () => {
  it('shows each CLI with its session and how to install a missing one', async () => {
    createFakeBackend()
    renderApp('/ajustes')

    const list = await screen.findByRole('list', { name: es.settings.clis.title })
    const [claude, agy] = within(list).getAllByRole('listitem')
    expect(claude).toHaveTextContent('Claude Code')
    expect(claude).toHaveTextContent('v2.1.296')
    expect(claude).toHaveTextContent(es.settings.clis.status.loggedIn)
    expect(agy).toHaveTextContent(es.settings.clis.status.notDetected)
    expect(agy).toHaveTextContent(es.settings.clis.notFound)
    expect(agy).toHaveTextContent(es.settings.clis.install.agy)
  })

  it('«Comprobar» probes the CLIs again', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')

    const [button] = await screen.findAllByRole('button', { name: es.settings.clis.check })
    await user.click(button)
    await waitFor(() =>
      expect(
        backend.callsTo('GET', '/api/clis').filter((c) => c.query === '?refresh=true'),
      ).toHaveLength(1),
    )
    expect(await screen.findByText(es.settings.clis.checked)).toBeVisible()
  })
})

describe('Settings · General', () => {
  it('shows the data folder with its size and moves it after confirmation', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')

    const field = await screen.findByLabelText(es.settings.general.dataDir)
    expect(field).toHaveValue('C:\\Users\\marta\\AppData\\Roaming\\AgenticOS')
    expect(screen.getByText(/1,8 GB/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: es.settings.general.change }))
    const dialog = await screen.findByRole('dialog', { name: es.settings.general.moveTitle })
    await user.type(within(dialog).getByLabelText(es.settings.general.moveTarget), 'D:\\Datos')
    await user.click(within(dialog).getByRole('button', { name: es.settings.general.moveConfirm }))

    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/settings/data-dir/move')[0]?.body).toEqual({
        to: 'D:\\Datos',
      }),
    )
    expect(await screen.findByText(es.settings.general.moving)).toBeVisible()
  })

  it('switches the theme', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')

    const themes = await screen.findByRole('tablist', { name: es.settings.general.theme })
    await user.click(within(themes).getByRole('tab', { name: es.settings.general.themes.light }))
    expect(document.documentElement).not.toHaveClass('dark')
    await user.click(within(themes).getByRole('tab', { name: es.settings.general.themes.dark }))
    expect(document.documentElement).toHaveClass('dark')
  })
})
