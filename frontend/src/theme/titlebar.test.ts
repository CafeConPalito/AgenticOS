import { invoke, isTauri } from '@tauri-apps/api/core'
import { BUILTIN_THEMES } from './builtin'
import { resolveTheme } from './resolve'
import { resetTitlebar, syncTitlebar } from './titlebar'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn(), isTauri: vi.fn() }))

const navy = resolveTheme('navy', [])
const light = resolveTheme('light', [])

describe('syncTitlebar', () => {
  beforeEach(() => {
    resetTitlebar()
    vi.mocked(invoke).mockReset().mockResolvedValue(undefined)
    vi.mocked(isTauri).mockReturnValue(true)
  })

  it('sends the page colors and the base of the theme to the shell', () => {
    syncTitlebar(navy)
    expect(invoke).toHaveBeenCalledWith('set_titlebar', {
      background: navy.colors.background,
      foreground: navy.colors.foreground,
      dark: true,
    })
    syncTitlebar(light)
    expect(invoke).toHaveBeenLastCalledWith('set_titlebar', {
      background: light.colors.background,
      foreground: light.colors.foreground,
      dark: false,
    })
  })

  it('does not repeat itself when nothing changed', () => {
    syncTitlebar(navy)
    syncTitlebar(navy)
    expect(invoke).toHaveBeenCalledTimes(1)
  })

  it('does nothing in a plain browser', () => {
    vi.mocked(isTauri).mockReturnValue(false)
    syncTitlebar(navy)
    expect(invoke).not.toHaveBeenCalled()
  })

  it('sends hex colors the shell can read, for every included theme', () => {
    for (const theme of BUILTIN_THEMES) {
      resetTitlebar()
      syncTitlebar(resolveTheme(theme.id, []))
      const args = vi.mocked(invoke).mock.lastCall?.[1] as {
        background: string
        foreground: string
      }
      expect(args.background).toMatch(/^#[0-9a-f]{6}$/i)
      expect(args.foreground).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })
})
