import { screen } from '@testing-library/react'
import es from '@/i18n/es.json'
import { CLIS, createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

describe('Dashboard · first start', () => {
  it('points to the detected CLIs when none is installed', async () => {
    createFakeBackend({ clis: CLIS.map((cli) => ({ ...cli, installed: false, path: null })) })
    renderApp('/')
    expect(await screen.findByText(es.cliReadiness.missingTitle)).toBeVisible()
    expect(screen.getByRole('link', { name: es.cliReadiness.open })).toHaveAttribute(
      'href',
      '/ajustes',
    )
  })

  it('asks to log in when the CLIs have no session', async () => {
    createFakeBackend({ clis: CLIS.map((cli) => ({ ...cli, installed: true, logged_in: false })) })
    renderApp('/')
    expect(await screen.findByText(es.cliReadiness.loggedOutTitle)).toBeVisible()
  })

  it('says nothing when a CLI is ready', async () => {
    createFakeBackend()
    renderApp('/')
    expect(await screen.findByRole('heading', { name: es.pages.dashboard.title })).toBeVisible()
    expect(screen.queryByText(es.cliReadiness.missingTitle)).not.toBeInTheDocument()
  })
})
