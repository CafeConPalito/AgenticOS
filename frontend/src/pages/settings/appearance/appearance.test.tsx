import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { DEFAULT_APPEARANCE, type ThemeDefinition } from '@/theme/model'
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

describe('Ajustes › Apariencia (phase 20, block 4)', () => {
  it('lists the built-in themes and uses one at once, saved in the backend', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia')
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

  it('follows the system with a theme for light and one for dark', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia')
    await user.click(await screen.findByRole('tab', { name: A.mode.system }))
    await waitFor(() => expect(backend.appearance.current.mode).toBe('system'))
    expect(screen.getByLabelText(A.mode.light_theme)).toBeVisible()
    expect(screen.getByLabelText(A.mode.dark_theme)).toBeVisible()
  })

  it('customizes a built-in theme in the editor, live, and saves it (CA7)', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/ajustes/apariencia')
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
    const child = mine({ id: 'hijo', name: 'Hijo', extends: 'mio' })
    const next = withoutTheme(
      {
        mode: 'system',
        theme: 'mio',
        light_theme: 'mio',
        dark_theme: 'mio',
        custom: [mine(), child],
      },
      'mio',
    )
    expect(next).toMatchObject({ theme: 'navy', light_theme: 'light', dark_theme: 'navy' })
    expect(next.custom).toEqual([{ ...child, extends: 'graphite' }])
  })
})
