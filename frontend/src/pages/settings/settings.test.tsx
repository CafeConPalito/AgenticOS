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

describe('Settings · Limpieza', () => {
  const branch = (name: string, merged: boolean, in_use = false) => ({
    name,
    task_id: null,
    task_code: name.replace('agentic/', ''),
    task_status: 'done',
    merged,
    last_commit: '2026-10-10T12:00:00+02:00',
    in_use,
  })

  it('changes the log retention and cleans the old logs', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')

    await user.click(await screen.findByRole('button', { name: es.settings.cleanup.cleanNow }))
    expect(await screen.findByText('3 logs borrados · 12,5 MB liberados')).toBeVisible()

    await user.click(screen.getByRole('combobox', { name: es.settings.cleanup.logs }))
    await user.click(await screen.findByRole('option', { name: es.settings.cleanup.never }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/maintenance')[0]?.body).toEqual({
        log_retention_days: null,
      }),
    )
    expect(screen.getByRole('button', { name: es.settings.cleanup.cleanNow })).toBeDisabled()
  })

  it('deletes merged branches, and an unmerged one only after confirming', async () => {
    const backend = createFakeBackend({
      branches: [
        {
          project_id: 'project-1',
          project_name: 'Tienda',
          error: null,
          branches: [
            branch('agentic/T-1', true),
            branch('agentic/T-2', false),
            branch('agentic/T-3', true, true),
          ],
        },
      ],
    })
    const user = userEvent.setup()
    renderApp('/ajustes')

    const list = await screen.findByRole('list', { name: 'Tienda' })
    expect(
      within(list).getByRole('button', { name: `${es.settings.cleanup.delete} agentic/T-3` }),
    ).toBeDisabled()

    await user.click(screen.getByRole('button', { name: es.settings.cleanup.deleteMerged }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/maintenance/branches/delete')[0]?.body).toEqual({
        project_id: 'project-1',
        branches: ['agentic/T-1'],
        force: false,
      }),
    )

    await user.click(
      await screen.findByRole('button', { name: `${es.settings.cleanup.delete} agentic/T-2` }),
    )
    const confirm = await screen.findByRole('alertdialog')
    await user.click(
      within(confirm).getByRole('button', { name: es.settings.cleanup.forceConfirm }),
    )
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/maintenance/branches/delete')[1]?.body).toEqual({
        project_id: 'project-1',
        branches: ['agentic/T-2'],
        force: true,
      }),
    )
  })
})

describe('Settings · Acerca de', () => {
  it('shows the version and where the data is', async () => {
    createFakeBackend()
    renderApp('/ajustes')
    const about = await screen.findByRole('region', { name: es.settings.about.title })
    await waitFor(() => expect(about).toHaveTextContent('0.1.0'))
    expect(about).toHaveTextContent('AgenticOS')
    expect(about).toHaveTextContent(es.settings.about.logsHint)
  })
})

describe('Settings · índice y atajos', () => {
  it('has an index with the six sections, linked to their anchors', async () => {
    createFakeBackend()
    renderApp('/ajustes')
    const index = await screen.findByRole('navigation', { name: es.settings.index })
    const links = within(index).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(Object.values(es.settings.sections))
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '#clis',
      '#general',
      '#notifications',
      '#limits',
      '#cleanup',
      '#about',
    ])
    for (const link of links) {
      const id = link.getAttribute('href')!.slice(1)
      expect(document.getElementById(id)).not.toBeNull()
    }
    expect(links[0]).toHaveAttribute('aria-current', 'true')
  })

  it('clicking an entry scrolls to its section and marks it', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    const index = await screen.findByRole('navigation', { name: es.settings.index })
    await user.click(within(index).getByRole('link', { name: es.settings.sections.limits }))
    expect(scroll).toHaveBeenCalled()
    expect(scroll.mock.contexts.at(-1)).toBe(document.getElementById('limits'))
    expect(within(index).getByRole('link', { name: es.settings.sections.limits })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('/ajustes#clis lands on the CLIs section', async () => {
    createFakeBackend()
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    renderApp('/ajustes#notifications')
    await screen.findByRole('navigation', { name: es.settings.index })
    await waitFor(() =>
      expect(scroll.mock.contexts.at(-1)).toBe(document.getElementById('notifications')),
    )
  })

  it('the «Atajos de una tecla» switch turns N and ? off and on', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const toggle = await screen.findByRole('switch', { name: es.settings.general.singleKey })
    expect(toggle).toBeChecked()

    await user.click(toggle)
    expect(toggle).not.toBeChecked()
    await user.keyboard('?')
    expect(screen.queryByRole('dialog')).toBeNull()

    await user.click(toggle)
    await user.keyboard('?')
    expect(await screen.findByRole('dialog', { name: es.shortcuts.title })).toBeVisible()
  })
})
