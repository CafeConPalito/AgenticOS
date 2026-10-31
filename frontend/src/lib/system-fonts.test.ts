import { fakeCanvas } from '@/test/fake-canvas'
import { isFontMissing, listSystemFonts, paintsByName } from './system-fonts'

const tauri = vi.hoisted(() => ({
  on: false,
  invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(),
}))
vi.mock('@tauri-apps/api/core', async (original) => ({
  ...(await original<typeof import('@tauri-apps/api/core')>()),
  isTauri: () => tauri.on,
  invoke: (cmd: string, args?: unknown) => tauri.invoke(cmd, args),
}))

type FontWindow = { queryLocalFonts?: () => Promise<{ family: string }[]> }

afterEach(() => {
  tauri.on = false
  tauri.invoke.mockReset()
  delete (window as unknown as FontWindow).queryLocalFonts
  vi.restoreAllMocks()
})

describe('system fonts (phase 22)', () => {
  it('in the desktop app the shell lists them', async () => {
    tauri.on = true
    tauri.invoke.mockResolvedValue(['Arial', 'Cascadia Code'])
    await expect(listSystemFonts()).resolves.toEqual(['Arial', 'Cascadia Code'])
    expect(tauri.invoke).toHaveBeenCalledWith('system_fonts', undefined)
  })

  it('in a browser with Local Font Access: each family once, sorted', async () => {
    ;(window as unknown as FontWindow).queryLocalFonts = () =>
      Promise.resolve([
        { family: 'Segoe UI' },
        { family: 'arial' },
        { family: 'Segoe UI' },
        { family: 'Ébano' },
      ])
    await expect(listSystemFonts()).resolves.toEqual(['arial', 'Ébano', 'Segoe UI'])
  })

  it('null when the browser has no access or the permission is refused', async () => {
    await expect(listSystemFonts()).resolves.toBeNull()
    ;(window as unknown as FontWindow).queryLocalFonts = () =>
      Promise.reject(new DOMException('denied', 'NotAllowedError'))
    await expect(listSystemFonts()).resolves.toBeNull()
  })

  it('tells the fonts the webview paints by name from those it does not', () => {
    fakeCanvas(['Cascadia Code'])
    expect(paintsByName('Cascadia Code')).toBe(true)
    expect(paintsByName('Sitka')).toBe(false)
  })

  it('a font is missing when the list lacks it, or when it is not painted without a list', () => {
    fakeCanvas(['Cascadia Code'])
    expect(isFontMissing('cascadia code', ['Arial', 'Cascadia Code'])).toBe(false)
    expect(isFontMissing('Fuente Rara', ['Arial'])).toBe(true)
    expect(isFontMissing('Cascadia Code', null)).toBe(false)
    expect(isFontMissing('Fuente Rara', undefined)).toBe(true)
  })
})
