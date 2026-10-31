import { screen, waitFor } from '@testing-library/react'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { mockHealth, renderApp } from '@/test/render'
import { APPLIED_KEY } from './apply'
import { DEFAULT_APPEARANCE } from './model'
import { APPEARANCE_STORAGE_KEY, THEME_STORAGE_KEY } from './ThemeProvider'

const root = () => document.documentElement
const cssVar = (name: string) => root().style.getPropertyValue(name)

function setSystemDark(dark: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: dark,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

afterEach(() => {
  setSystemDark(false)
  root().removeAttribute('style')
  root().classList.add('dark')
})

describe('theme', () => {
  it('defaults to the navy dark theme, with no light/dark switch (phase 22)', async () => {
    mockHealth('ok')
    renderApp('/')
    expect(await screen.findByRole('button', { name: es.dock.toggle })).toBeVisible()
    expect(root()).toHaveClass('dark')
    expect(cssVar('--background')).toBe('#0a1a33')
    expect(screen.queryByRole('button', { name: /tema (claro|oscuro)/i })).toBeNull()
  })

  it('takes the theme saved in the backend and remembers it here', async () => {
    createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, theme: 'warm' } })
    renderApp('/')
    await waitFor(() => expect(cssVar('--background')).toBe('#f6efe5'))
    expect(root()).not.toHaveClass('dark')
    expect(JSON.parse(localStorage.getItem(APPEARANCE_STORAGE_KEY)!).theme).toBe('warm')
    expect(JSON.parse(localStorage.getItem(APPLIED_KEY)!).base).toBe('light')
  })

  it('carries over the light theme chosen before phase 20', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    const backend = createFakeBackend()
    renderApp('/')
    await waitFor(() => expect(backend.appearance.current.theme).toBe('light'))
    expect(cssVar('--background')).toBe('#f4f6fa')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
  })

  it.each([
    [true, 'graphite', '#17181b'],
    [false, 'warm', '#f6efe5'],
  ])(
    'keeps the theme on screen of a phase 20 document that followed the system (dark %s)',
    async (dark, theme, background) => {
      setSystemDark(dark)
      const backend = createFakeBackend({
        appearance: {
          ...DEFAULT_APPEARANCE,
          legacy_follow: { light_theme: 'warm', dark_theme: 'graphite' },
        } as typeof DEFAULT_APPEARANCE,
      })
      renderApp('/')
      await waitFor(() => expect(cssVar('--background')).toBe(background))
      await waitFor(() => expect(backend.appearance.current).toEqual({ theme, custom: [] }))
    },
  )

  it('reads a copy of phase 20 that followed the system while the backend is away', async () => {
    mockHealth('ok')
    setSystemDark(true)
    localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({
        mode: 'system',
        theme: 'navy',
        light_theme: 'warm',
        dark_theme: 'contrast',
        custom: [],
      }),
    )
    renderApp('/')
    await waitFor(() => expect(cssVar('--background')).toBe('#000000'))
  })

  it('applies a theme made from scratch with a font of the system', async () => {
    createFakeBackend({
      appearance: {
        theme: 'cero',
        custom: [
          {
            format: 'agentic-os.theme',
            version: 2,
            id: 'cero',
            name: 'Cero',
            base: 'light',
            colors: { background: '#fafafa' },
            font_family: 'Cascadia Code',
          },
        ],
      },
    })
    renderApp('/')
    await waitFor(() => expect(cssVar('--background')).toBe('#fafafa'))
    expect(cssVar('--foreground')).toBe('#0a1a33') // from the light base set
    expect(cssVar('--app-font')).toBe(`"Cascadia Code", system-ui, 'Segoe UI', sans-serif`)
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
