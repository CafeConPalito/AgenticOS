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
