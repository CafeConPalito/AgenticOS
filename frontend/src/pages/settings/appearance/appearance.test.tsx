import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { DEFAULT_APPEARANCE, type ThemeDefinition } from '@/theme/model'
import { FILTER_STORAGE_KEY } from './AppearancePage'
import { freeId, parseTheme, withoutTheme } from './theme-io'

const A = es.appearance
const E = A.editor
const cssVar = (name: string) => document.documentElement.style.getPropertyValue(name)

const mine = (changes: Partial<ThemeDefinition> = {}): ThemeDefinition => ({
  format: 'agentic-os.theme',
  version: 1,
  id: 'mio',
  name: 'Mío',
  base: 'dark',
  extends: 'graphite',
  colors: { 'primary-action': '#aa3377' },
  ...changes,
})

afterEach(() => {
  document.documentElement.removeAttribute('style')
  document.documentElement.classList.add('dark')
})

/** The gallery shows every theme (it starts with the system's light or dark ones). */
async function showAll(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('tab', { name: A.filter.all }))
}

const names = () =>
  screen
    .getAllByRole('listitem')
    .map((item) => item.getAttribute('aria-label'))
    .filter(Boolean)

describe('Ajustes › Apariencia (phase 20, block 4)', () => {
  it('lists the built-in themes and uses one at once, saved in the backend', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia')
    await showAll(user)
    for (const name of Object.values(A.builtin))
      expect(await screen.findByRole('listitem', { name })).toBeVisible()
    expect(screen.getByRole('listitem', { name: A.builtin.navy })).toHaveAttribute(
      'aria-current',
      'true',
    )

    const warm = screen.getByRole('listitem', { name: A.builtin.warm })
    await user.click(within(warm).getByRole('button', { name: A.use }))
    await waitFor(() => expect(cssVar('--background')).toBe('#f6efe5'))
    await waitFor(() => expect(backend.appearance.current.theme).toBe('warm'))
    expect(screen.getByRole('listitem', { name: A.builtin.warm })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('filters light and dark themes, custom ones too, and remembers it (phase 22)', async () => {
    const light = mine({ id: 'claro', name: 'Mi claro', base: 'light', extends: 'warm' })
    createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, custom: [mine(), light] } })
    const user = userEvent.setup()
    const { unmount } = renderApp('/ajustes/apariencia')
    // The system is light here: the light themes, and navy (in use) first, still in sight.
    expect(await screen.findByRole('tab', { name: A.filter.light })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await screen.findByRole('listitem', { name: 'Mi claro' })
    expect(names()[0]).toBe(A.builtin.navy)
    expect(names()).toContain(A.builtin.warm)
    expect(names()).not.toContain(A.builtin.graphite)
    expect(names()).not.toContain('Mío')

    await user.click(screen.getByRole('tab', { name: A.filter.dark }))
    expect(names()).toContain('Mío')
    expect(names()).toContain(A.builtin.graphite)
    expect(names()).not.toContain('Mi claro')
    expect(localStorage.getItem(FILTER_STORAGE_KEY)).toBe('dark')

    unmount()
    renderApp('/ajustes/apariencia')
    expect(await screen.findByRole('tab', { name: A.filter.dark })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('starts with the dark themes when the system is dark, with no «Seguir al sistema»', async () => {
    const original = window.matchMedia
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: true,
    })) as typeof window.matchMedia
    try {
      createFakeBackend()
      renderApp('/ajustes/apariencia')
      expect(await screen.findByRole('tab', { name: A.filter.dark })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      expect(screen.queryByText('Seguir al sistema')).toBeNull()
    } finally {
      window.matchMedia = original
    }
  })

  it('«Nuevo tema» makes one from scratch, edits, saves and exports it', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/ajustes/apariencia')
    await user.click(await screen.findByRole('button', { name: A.create.action }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(A.create.name), 'De cero')
    await user.click(within(dialog).getByRole('tab', { name: E.bases.dark }))
    await user.click(within(dialog).getByRole('button', { name: A.create.submit }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/ajustes/apariencia/de-cero'))
    expect(backend.appearance.current.custom[0]).toEqual({
      format: 'agentic-os.theme',
      version: 2,
      id: 'de-cero',
      name: 'De cero',
      base: 'dark',
      colors: {},
    })
    // The navy base set underneath, previewed live.
    await waitFor(() => expect(cssVar('--background')).toBe('#0a1a33'))
    expect(screen.getByRole('combobox', { name: E.extends })).toHaveTextContent(E.extendsNone)
    const background = screen.getByLabelText(A.tokens.background, {
      selector: 'input:not([type="color"])',
    })
    await user.clear(background)
    await user.type(background, '#101010')
    await user.click(screen.getByRole('button', { name: E.saveAndUse }))
    await waitFor(() =>
      expect(backend.appearance.current).toMatchObject({
        theme: 'de-cero',
        custom: [{ id: 'de-cero', colors: { background: '#101010' } }],
      }),
    )
    // What is exported imports back as it is.
    const file = JSON.stringify(backend.appearance.current.custom[0])
    const again = parseTheme(file, DEFAULT_APPEARANCE)
    expect(again).toMatchObject({ ok: true, theme: { id: 'de-cero', base: 'dark' } })
    expect(again.ok && again.theme.extends).toBeFalsy()
  })

  it('customizes a built-in theme in the editor, live, and saves it (CA7)', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/ajustes/apariencia')
    await showAll(user)
    const graphite = await screen.findByRole('listitem', { name: A.builtin.graphite })
    await user.click(within(graphite).getByRole('button', { name: `Más acciones de «Grafito»` }))
    await user.click(await screen.findByRole('menuitem', { name: A.customize }))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/ajustes/apariencia/grafito-copia'),
    )
    expect(backend.appearance.current.custom[0]).toMatchObject({
      id: 'grafito-copia',
      name: 'Grafito (copia)',
      extends: 'graphite',
      base: 'dark',
    })

    // The whole app shows the draft while editing.
    const action = await screen.findByLabelText(A.tokens['primary-action'], {
      selector: 'input:not([type="color"])',
    })
    await user.clear(action)
    await user.type(action, '#aa3377')
    await waitFor(() => expect(cssVar('--primary-action')).toBe('#aa3377'))
    expect(cssVar('--background')).toBe('#17181b') // still graphite underneath

    // A text that reads badly is reported, without blocking.
    const muted = screen.getByLabelText(A.tokens['muted-foreground'], {
      selector: 'input:not([type="color"])',
    })
    await user.clear(muted)
    await user.type(muted, '#2a2b30')
    expect(await screen.findByRole('status', { name: E.contrast.title })).toHaveTextContent(
      /Texto atenuado sobre Fondo/,
    )

    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.appearance.current.custom[0].colors).toEqual({
        'primary-action': '#aa3377',
        'muted-foreground': '#2a2b30',
      }),
    )
  })

  it('«Descartar» drops the changes and leaving the editor stops the preview', async () => {
    createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, custom: [mine()] } })
    const user = userEvent.setup()
    const { router } = renderApp('/ajustes/apariencia/mio')
    const action = await screen.findByLabelText(A.tokens['primary-action'], {
      selector: 'input:not([type="color"])',
    })
    expect(action).toHaveValue('#aa3377')
    await user.clear(action)
    await user.type(action, '#123456')
    await waitFor(() => expect(cssVar('--primary-action')).toBe('#123456'))
    await user.click(screen.getByRole('button', { name: E.discard }))
    await waitFor(() => expect(cssVar('--primary-action')).toBe('#aa3377'))

    await user.click(screen.getByRole('button', { name: es.header.back }))
    await waitFor(() => expect(router.state.location.pathname).not.toMatch(/mio$/))
    // Navy is in use: its value comes back once the editor is gone.
    await waitFor(() => expect(cssVar('--primary-action')).toBe('#2e5bd6'))
  })

  it('imports a theme file and refuses a broken one with the reason', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia')
    const input = await screen.findByLabelText(A.import.label)

    const good = new File([JSON.stringify(mine())], 'mio.theme.json', { type: 'application/json' })
    await user.upload(input, good)
    await waitFor(() => expect(backend.appearance.current.custom.map((c) => c.id)).toEqual(['mio']))
    expect(await screen.findByText('Tema «Mío» importado')).toBeVisible()

    await user.upload(input, new File(['{ nope'], 'x.json'))
    expect(await screen.findByText(A.import.json)).toBeVisible()
    await user.upload(input, new File([JSON.stringify(mine({ extends: 'ghost' }))], 'x.json'))
    expect(await screen.findByText(/parte de «ghost»/)).toBeVisible()
    expect(backend.appearance.current.custom).toHaveLength(1)
  })

  it('deletes a theme in use and goes back to navy', async () => {
    const backend = createFakeBackend({
      appearance: { ...DEFAULT_APPEARANCE, theme: 'mio', custom: [mine()] },
    })
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia')
    // The theme in use is in sight whatever the filter.
    const card = await screen.findByRole('listitem', { name: 'Mío' })
    await user.click(within(card).getByRole('button', { name: 'Más acciones de «Mío»' }))
    await user.click(await screen.findByRole('menuitem', { name: es.common.delete }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: es.common.delete,
      }),
    )
    await waitFor(() =>
      expect(backend.appearance.current).toMatchObject({ theme: 'navy', custom: [] }),
    )
  })
})

describe('theme files (phase 20)', () => {
  it('makes free ids from names', () => {
    expect(freeId('Mi tema cálido', [])).toBe('mi-tema-calido')
    expect(freeId('Mío', ['mio'])).toBe('mio-2')
    expect(freeId('Navy', [])).toBe('navy-2')
    expect(freeId('¡¡!!', [])).toBe('tema')
  })

  it('reads a theme, renames a clashing id and refuses what does not fit', () => {
    const appearance = { ...DEFAULT_APPEARANCE, custom: [mine()] }
    const again = parseTheme(JSON.stringify(mine()), appearance)
    expect(again).toMatchObject({ ok: true, renamed: true, theme: { id: 'mio-2' } })
    expect(parseTheme('[]', appearance)).toMatchObject({ ok: false, reason: 'field' })
    expect(
      parseTheme(JSON.stringify(mine({ colors: { background: 'red' } })), appearance),
    ).toMatchObject({ ok: false, reason: 'field', field: 'colors.background' })
    expect(parseTheme(JSON.stringify({ ...mine(), extra: 1 }), appearance)).toMatchObject({
      ok: false,
      reason: 'field',
    })
  })

  it('removing a theme reassigns what used it and the themes that extended it', () => {
    const child = mine({ id: 'hijo', name: 'Hijo', extends: 'mio', colors: { border: '#111111' } })
    const next = withoutTheme({ theme: 'mio', custom: [mine({ font: 'inter' }), child] }, 'mio')
    expect(next.theme).toBe('navy')
    // The child takes in what it inherited, so it looks the same.
    expect(next.custom).toEqual([
      {
        ...child,
        extends: 'graphite',
        colors: { 'primary-action': '#aa3377', border: '#111111' },
        font: 'inter',
      },
    ])
    // A child with its own font did not show the parent's font of the system: still so.
    const own = mine({ id: 'propio', name: 'Propio', extends: 'mio', font: 'inter' })
    const parent = mine({ font_family: 'Cascadia Code' })
    const kept = withoutTheme({ theme: 'navy', custom: [parent, own] }, 'mio').custom[0]
    expect(kept.font).toBe('inter')
    expect(kept.font_family).toBeUndefined()
    const scratch = mine({ extends: undefined, font_family: 'Cascadia Code' })
    const orphan = withoutTheme({ theme: 'navy', custom: [scratch, child] }, 'mio').custom[0]
    expect(orphan.extends).toBeUndefined()
    expect(orphan.font_family).toBe('Cascadia Code')
  })

  it('reads a theme file exported in phase 20 (v1)', () => {
    const v1 = {
      format: 'agentic-os.theme',
      version: 1,
      id: 'mi-calido',
      name: 'Mi cálido',
      base: 'light',
      extends: 'warm',
      colors: { background: '#fdf6ec', 'primary-action': '#a4441c' },
      font: 'atkinson',
      scale: 1.1,
      density: 'comfortable',
      radius: 14,
    }
    expect(parseTheme(JSON.stringify(v1), DEFAULT_APPEARANCE)).toMatchObject({
      ok: true,
      renamed: false,
      theme: v1,
    })
    const injected = JSON.stringify({ ...v1, font_family: 'x"; } body {' })
    expect(parseTheme(injected, DEFAULT_APPEARANCE)).toMatchObject({
      ok: false,
      reason: 'field',
      field: 'font_family',
    })
  })
})
