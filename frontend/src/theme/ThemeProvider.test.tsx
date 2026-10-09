import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { mockHealth, renderApp } from '@/test/render'
import { THEME_STORAGE_KEY } from './ThemeProvider'

describe('theme', () => {
  it('defaults to the navy dark theme', async () => {
    mockHealth('ok')
    renderApp('/')
    expect(await screen.findByText(es.theme.toLight)).toBeVisible()
    expect(document.documentElement).toHaveClass('dark')
  })

  it('switches to light and remembers the choice', async () => {
    mockHealth('ok')
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByText(es.theme.toLight))
    expect(document.documentElement).not.toHaveClass('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(screen.getByText(es.theme.toDark)).toBeVisible()
  })

  it('restores a stored light theme on start', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    mockHealth('ok')
    renderApp('/')
    expect(await screen.findByText(es.theme.toDark)).toBeVisible()
    expect(document.documentElement).not.toHaveClass('dark')
  })
})
