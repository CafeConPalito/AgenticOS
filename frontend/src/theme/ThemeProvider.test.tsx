import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { mockHealth, renderApp } from '@/test/render'
import { APPLIED_KEY } from './apply'
import { DEFAULT_APPEARANCE } from './model'
import { APPEARANCE_STORAGE_KEY, THEME_STORAGE_KEY } from './ThemeProvider'

const root = () => document.documentElement
const cssVar = (name: string) => root().style.getPropertyValue(name)

function setSystemDark(dark: boolean) {
  const listeners: ((e: MediaQueryListEvent) => void)[] = []
  window.matchMedia = ((query: string) => ({
    matches: dark,
    media: query,
    onchange: null,
    addEventListener: (_: string, fn: (e: MediaQueryListEvent) => void) => listeners.push(fn),
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  return (next: boolean) => {
    for (const fn of listeners) fn({ matches: next } as MediaQueryListEvent)
  }
}

afterEach(() => {
  setSystemDark(false)
  root().removeAttribute('style')
  root().classList.add('dark')
})

describe('theme', () => {
  it('defaults to the navy dark theme', async () => {
    mockHealth('ok')
    renderApp('/')
    expect(await screen.findByRole('button', { name: es.theme.toLight })).toBeVisible()
    expect(root()).toHaveClass('dark')
    expect(cssVar('--background')).toBe('#0a1a33')
  })

  it('switches to light, saves it in the backend and remembers it here', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: es.theme.toLight }))
    expect(root()).not.toHaveClass('dark')
    expect(cssVar('--background')).toBe('#f4f6fa')
    await waitFor(() => expect(backend.appearance.current.theme).toBe('light'))
    expect(JSON.parse(localStorage.getItem(APPEARANCE_STORAGE_KEY)!).theme).toBe('light')
    expect(JSON.parse(localStorage.getItem(APPLIED_KEY)!).base).toBe('light')
    expect(screen.getByRole('button', { name: es.theme.toDark })).toBeVisible()
  })

  it('takes the theme saved in the backend', async () => {
    createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, theme: 'warm' } })
    renderApp('/')
    await waitFor(() => expect(cssVar('--background')).toBe('#f6efe5'))
    expect(root()).not.toHaveClass('dark')
  })

  it('carries over the light theme chosen before phase 20', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    const backend = createFakeBackend()
    renderApp('/')
    expect(await screen.findByRole('button', { name: es.theme.toDark })).toBeVisible()
    await waitFor(() => expect(backend.appearance.current.theme).toBe('light'))
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
  })

  it('follows the system and changes live', async () => {
    const change = setSystemDark(false)
    createFakeBackend({
      appearance: {
        ...DEFAULT_APPEARANCE,
        mode: 'system',
        light_theme: 'warm',
        dark_theme: 'graphite',
      },
    })
    renderApp('/')
    await waitFor(() => expect(cssVar('--background')).toBe('#f6efe5'))
    change(true)
    await waitFor(() => expect(cssVar('--background')).toBe('#17181b'))
    expect(root()).toHaveClass('dark')
  })

  it('applies a custom theme over the one it extends', async () => {
    createFakeBackend({
      appearance: {
        ...DEFAULT_APPEARANCE,
        theme: 'mio',
        custom: [
          {
            format: 'agentic-os.theme',
            version: 1,
            id: 'mio',
            name: 'Mío',
            base: 'dark',
            extends: 'graphite',
            colors: { 'primary-action': '#aa3377' },
            font: 'atkinson',
            density: 'compact',
            radius: 4,
          },
        ],
      },
    })
    renderApp('/')
    await waitFor(() => expect(cssVar('--primary-action')).toBe('#aa3377'))
    expect(cssVar('--background')).toBe('#17181b') // from graphite
    expect(cssVar('--app-font')).toContain('Atkinson Hyperlegible')
    expect(cssVar('--spacing')).toBe('0.22rem')
    expect(cssVar('--radius')).toBe('0.25rem')
  })

  it('ignores an answer that is not an appearance', async () => {
    mockHealth('ok') // answers the health body to every request
    localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({ ...DEFAULT_APPEARANCE, theme: 'contrast' }),
    )
    renderApp('/')
    await waitFor(() => expect(cssVar('--background')).toBe('#000000'))
  })
})
