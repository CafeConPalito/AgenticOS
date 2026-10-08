import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { mockHealth, renderApp } from '@/test/render'

const SECTIONS = ['dashboard', 'agents', 'projects', 'board', 'inbox', 'usage', 'settings'] as const

describe('AppSidebar', () => {
  it('shows the 7 sections with their Spanish labels', async () => {
    mockHealth('ok')
    renderApp('/')
    const nav = await screen.findByRole('navigation', { name: es.nav.main })
    const links = within(nav).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(SECTIONS.map((s) => es.nav[s]))
  })

  it('navigates between sections and marks the active one', async () => {
    mockHealth('ok')
    const user = userEvent.setup()
    const { router } = renderApp('/')
    expect(await screen.findByRole('heading', { name: es.pages.dashboard.title })).toBeVisible()

    const nav = screen.getByRole('navigation', { name: es.nav.main })
    await user.click(within(nav).getByRole('link', { name: es.nav.agents }))
    expect(router.state.location.pathname).toBe('/agentes')
    expect(screen.getByRole('heading', { name: es.pages.agents.title })).toBeVisible()
    expect(within(nav).getByRole('link', { name: es.nav.agents })).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(within(nav).getByRole('link', { name: es.nav.dashboard })).toHaveAttribute(
      'data-active',
      'false',
    )
  })

  it('redirects unknown routes to the dashboard', async () => {
    mockHealth('ok')
    const { router } = renderApp('/no-existe')
    expect(await screen.findByRole('heading', { name: es.pages.dashboard.title })).toBeVisible()
    expect(router.state.location.pathname).toBe('/')
  })
})
