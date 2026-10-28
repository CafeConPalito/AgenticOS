import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { bugReportHref } from '@/lib/bug-report'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { DEFAULT_APPEARANCE } from '@/theme/model'

const A = es.about

describe('Acerca de (phase 20, block 7; CA10, CA11)', () => {
  it('says who made the app, with the logo for the theme', async () => {
    createFakeBackend()
    renderApp('/acerca-de')
    const authors = await screen.findByRole('region', { name: A.authors })
    expect(within(authors).getByText(A.madeBy)).toBeVisible()
    expect(within(authors).getByText(A.author)).toBeVisible()
    // Navy is dark: the white (negative) logo.
    expect(within(authors).getByAltText('Café con Palito').getAttribute('src')).toMatch(/negative/)
  })

  it('uses the normal logo on a light theme', async () => {
    createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, theme: 'warm' } })
    renderApp('/acerca-de')
    const logo = await screen.findByAltText('Café con Palito')
    await waitFor(() => expect(logo.getAttribute('src')).not.toMatch(/negative/))
  })

  it('shows the GPLv3 summary and its full text, offline', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/acerca-de')
    const license = await screen.findByRole('region', { name: A.license.title })
    expect(license).toHaveTextContent(A.copyright)
    await user.click(within(license).getByText(A.license.full))
    expect(await within(license).findByText(/GNU GENERAL PUBLIC LICENSE/)).toBeVisible()
    expect(license).toHaveTextContent('Version 3, 29 June 2007')
  })

  it('lists the third-party licenses, searchable and by origin', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    renderApp('/acerca-de')
    const third = await screen.findByRole('region', { name: A.thirdParty.title })
    await waitFor(() => expect(within(third).getAllByRole('row').length).toBeGreaterThan(500))
    await user.type(within(third).getByLabelText(A.thirdParty.search), 'react-easy-crop')
    expect(within(third).getAllByRole('row')).toHaveLength(2) // header + one
    expect(within(third).getByText('MIT')).toBeVisible()
    await user.clear(within(third).getByLabelText(A.thirdParty.search))
    await user.click(within(third).getByRole('tab', { name: A.thirdParty.ecosystems.rust }))
    expect(within(third).getByText('tauri')).toBeVisible()
    expect(within(third).queryByText('react')).toBeNull()
  })

  it('«Informar de un error» writes to contacto@cafeconpalito.com', async () => {
    createFakeBackend()
    renderApp('/acerca-de')
    const help = await screen.findByRole('region', { name: A.help.title })
    const link = within(help).getByRole('link', { name: A.help.report })
    const href = link.getAttribute('href')!
    expect(href).toMatch(/^mailto:contacto@cafeconpalito\.com\?subject=/)
    const params = new URLSearchParams(href.split('?')[1])
    expect(params.get('subject')).toBe(`${A.bug.subject} · Agentic OS ${__APP_VERSION__}`)
    expect(params.get('body')).toContain(A.bug.happened)
  })

  it('is in the palette and has its breadcrumb', async () => {
    createFakeBackend()
    renderApp('/acerca-de')
    expect(await screen.findByRole('navigation', { name: /breadcrumb/i })).toHaveTextContent(
      es.nav.about,
    )
  })
})

describe('bug report link', () => {
  const texts = {
    subject: 'Error',
    doing: 'Haciendo:',
    expected: 'Esperaba:',
    happened: 'Pasó:',
    logs: 'Logs',
  }

  it('names the backend version only when it differs, and stays short', () => {
    const same = bugReportHref({ version: '1.2.0', backendVersion: '1.2.0', system: 'Win', texts })
    expect(decodeURIComponent(same)).not.toContain('backend')
    const other = bugReportHref({ version: '1.2.0', backendVersion: '1.1.0', system: 'Win', texts })
    expect(decodeURIComponent(other)).toContain('Agentic OS 1.2.0 · backend 1.1.0')
    expect(other.length).toBeLessThan(1600)
  })
})
