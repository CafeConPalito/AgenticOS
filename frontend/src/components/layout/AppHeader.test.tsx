import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makeInboxItem,
  makeProject,
  makeRun,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

function seedBusy() {
  const agent = makeAgent()
  const project = makeProject()
  const task = makeTask({ agent_id: agent.id, project_id: project.id, status: 'running' })
  const queued = makeTask({ agent_id: agent.id, project_id: project.id, status: 'queued' })
  const run = makeRun({ agent_id: agent.id, project_id: project.id, task_id: task.id })
  createFakeBackend({ agents: [agent], projects: [project], tasks: [task, queued], runs: [run] })
  return { agent, project, task }
}

describe('AppHeader', () => {
  it('has the top navigation with live counters and no sidebar', async () => {
    seedBusy()
    renderApp('/')
    const nav = await screen.findByRole('navigation', { name: es.nav.main })
    const links = within(nav).getAllByRole('link')
    expect(links.map((l) => l.textContent?.replace(/\d+$/, ''))).toEqual([
      `${es.nav.board}`,
      `${es.nav.runs}`,
      `${es.nav.settings}`,
    ])
    expect(await within(nav).findByRole('link', { name: `${es.nav.board}2` })).toBeVisible()
    expect(within(nav).getByRole('link', { name: `${es.nav.runs}1` })).toBeVisible()
    expect(document.querySelector('[data-sidebar]')).toBeNull()
  })

  it('marks the active section with aria-current', async () => {
    seedBusy()
    renderApp('/ejecuciones')
    const nav = await screen.findByRole('navigation', { name: es.nav.main })
    expect(within(nav).getByRole('link', { name: new RegExp(es.nav.runs) })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(nav).getByRole('link', { name: new RegExp(es.nav.board) })).not.toHaveAttribute(
      'aria-current',
    )
  })

  it('keeps second-level pages out of the bar: no current section there', async () => {
    seedBusy()
    renderApp('/consumo')
    const nav = await screen.findByRole('navigation', { name: es.nav.main })
    expect(within(nav).queryByRole('link', { name: es.nav.usage })).toBeNull()
    expect(within(nav).queryAllByRole('link', { current: 'page' })).toHaveLength(0)
  })

  it('has no «Volver» at home and goes back in the history elsewhere', async () => {
    seedBusy()
    const user = userEvent.setup()
    const { router } = renderApp('/')
    await screen.findByRole('navigation', { name: es.nav.main })
    expect(screen.queryByRole('button', { name: es.header.back })).toBeNull()

    await user.click(screen.getByRole('link', { name: new RegExp(es.nav.runs) }))
    expect(router.state.location.pathname).toBe('/ejecuciones')
    await user.click(screen.getByRole('button', { name: es.header.back }))
    expect(router.state.location.pathname).toBe('/')
  })

  it('«Volver» goes to the parent page when the app opened deep in a route', async () => {
    const { agent } = seedBusy()
    const user = userEvent.setup()
    const { router } = renderApp(`/agentes/${agent.id}/general`)
    await user.click(await screen.findByRole('button', { name: es.header.back }))
    expect(router.state.location.pathname).toBe('/agentes')
  })

  it('goes forward again after going back, and only then (phase 20)', async () => {
    seedBusy()
    const user = userEvent.setup()
    const { router } = renderApp('/')
    await screen.findByRole('navigation', { name: es.nav.main })
    await user.click(screen.getByRole('link', { name: new RegExp(es.nav.runs) }))
    expect(screen.getByRole('button', { name: es.header.forward })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: es.header.back }))
    expect(router.state.location.pathname).toBe('/')
    // At home with somewhere to go forward: both buttons stay, «Volver» disabled.
    expect(screen.getByRole('button', { name: es.header.back })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: es.header.forward }))
    expect(router.state.location.pathname).toBe('/ejecuciones')
    expect(screen.getByRole('button', { name: es.header.forward })).toBeDisabled()
  })

  it('a new page after going back drops what was ahead', async () => {
    seedBusy()
    const user = userEvent.setup()
    const { router } = renderApp('/')
    // The main navigation's tabs: Inicio's shortcuts (phase 23) have the same names.
    const nav = await screen.findByRole('navigation', { name: es.nav.main })
    await user.click(within(nav).getByRole('link', { name: new RegExp(es.nav.runs) }))
    await user.click(screen.getByRole('button', { name: es.header.back }))
    await user.click(within(nav).getByRole('link', { name: new RegExp(es.nav.board) }))
    expect(router.state.location.pathname).toBe('/tablero')
    expect(screen.getByRole('button', { name: es.header.forward })).toBeDisabled()
  })

  it('shows the pending Inbox items and opens the Inbox (phase 20)', async () => {
    createFakeBackend({
      inbox: [makeInboxItem(), makeInboxItem(), makeInboxItem({ status: 'resolved' })],
    })
    const user = userEvent.setup()
    const { router } = renderApp('/')
    const link = await screen.findByRole('link', { name: 'Inbox · 2 pendientes' })
    expect(link).toHaveTextContent('2')
    await user.click(link)
    expect(router.state.location.pathname).toBe('/inbox')
    expect(screen.getByRole('link', { name: 'Inbox · 2 pendientes' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('shows no number when the Inbox is empty', async () => {
    createFakeBackend({})
    renderApp('/')
    const link = await screen.findByRole('link', { name: 'Inbox · 0 pendientes' })
    expect(link).not.toHaveTextContent(/\d/)
  })

  it('the logo goes home', async () => {
    seedBusy()
    const user = userEvent.setup()
    const { router } = renderApp('/ajustes')
    await user.click(await screen.findByRole('link', { name: es.header.home }))
    expect(router.state.location.pathname).toBe('/')
  })
})
