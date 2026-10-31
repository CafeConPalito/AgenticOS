import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { fakeCanvas } from '@/test/fake-canvas'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { DEFAULT_APPEARANCE, type ThemeDefinition } from '@/theme/model'

const E = es.appearance.editor
const F = E.fonts
const cssVar = (name: string) => document.documentElement.style.getPropertyValue(name)
type FontWindow = { queryLocalFonts?: () => Promise<{ family: string }[]> }

const mine = (changes: Partial<ThemeDefinition> = {}): ThemeDefinition => ({
  format: 'agentic-os.theme',
  version: 2,
  id: 'mio',
  name: 'Mío',
  base: 'dark',
  colors: {},
  ...changes,
})

function systemFonts(families: string[]) {
  ;(window as unknown as FontWindow).queryLocalFonts = () =>
    Promise.resolve(families.map((family) => ({ family })))
}

afterEach(() => {
  delete (window as unknown as FontWindow).queryLocalFonts
  vi.restoreAllMocks()
  document.documentElement.removeAttribute('style')
})

describe('theme editor › font of the system (phase 22)', () => {
  it('searches the fonts of the system and applies one to the whole app (CA5)', async () => {
    systemFonts(['Arial', 'Cascadia Code', 'Sitka'])
    fakeCanvas(['Arial', 'Cascadia Code']) // Sitka is listed but not painted by its name
    const backend = createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, custom: [mine()] } })
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia/mio')

    await user.click(await screen.findByRole('combobox', { name: E.font }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(F.included)).toBeVisible()
    expect(await within(dialog).findByText('Cascadia Code')).toBeVisible()
    expect(within(dialog).queryByText('Sitka')).toBeNull()

    await user.type(within(dialog).getByPlaceholderText(F.search), 'casc')
    expect(within(dialog).queryByText('Arial')).toBeNull()
    await user.click(within(dialog).getByText('Cascadia Code'))
    await waitFor(() => expect(cssVar('--app-font')).toMatch(/^"Cascadia Code", system-ui/))
    expect(screen.getByRole('combobox', { name: E.font })).toHaveTextContent('Cascadia Code')

    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.appearance.current.custom[0].font_family).toBe('Cascadia Code'),
    )

    // Back to a font the app ships.
    await user.click(screen.getByRole('combobox', { name: E.font }))
    await user.click(await within(await screen.findByRole('dialog')).findByText(F.atkinson))
    await waitFor(() => expect(cssVar('--app-font')).toContain('Atkinson Hyperlegible'))
  })

  it('reports a font of the system missing on this machine (CA6)', async () => {
    fakeCanvas([])
    createFakeBackend({
      appearance: { ...DEFAULT_APPEARANCE, custom: [mine({ font_family: 'Fuente Rara' })] },
    })
    renderApp('/ajustes/apariencia/mio')
    expect(await screen.findByText(/«Fuente Rara» no está instalada/)).toBeVisible()
    // The system's font stands in.
    expect(cssVar('--app-font')).toContain('system-ui')
  })

  it('without a list of fonts the name is typed', async () => {
    fakeCanvas(['Cascadia Code'])
    const backend = createFakeBackend({ appearance: { ...DEFAULT_APPEARANCE, custom: [mine()] } })
    const user = userEvent.setup()
    renderApp('/ajustes/apariencia/mio')
    await user.click(await screen.findByRole('combobox', { name: E.font }))
    const typed = await screen.findByLabelText(F.typed)
    await user.type(typed, 'x"; }')
    expect(screen.getByRole('button', { name: F.use })).toBeDisabled()
    await user.clear(typed)
    await user.type(typed, 'Cascadia Code')
    await user.click(screen.getByRole('button', { name: F.use }))
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.appearance.current.custom[0].font_family).toBe('Cascadia Code'),
    )
  })
})
