import { PALETTES } from './builtin-palettes'
import { BUILTIN_IDS, BUILTIN_THEMES } from './builtin'
import { AA, contrastRatio } from './contrast'
import { OWN_PALETTES, THEME_CREDITS } from './credits'
import { ensureContrast, fromPalette, mix } from './derive'
import { TOKEN_NAMES } from './model'
import generated from '@/generated/builtin-themes.json'

describe('themes from a palette (phase 22)', () => {
  it('mixes two colors', () => {
    expect(mix('#000000', '#ffffff', 0)).toBe('#000000')
    expect(mix('#000000', '#ffffff', 0.5)).toBe('#808080')
    expect(mix('#102030', '#102030', 0.7)).toBe('#102030')
  })

  it('leaves a color that already reads as it is', () => {
    expect(ensureContrast('#000000', ['#ffffff'], AA)).toBe('#000000')
    expect(ensureContrast('#6272a4', ['#ffffff'], AA)).toBe('#6272a4')
  })

  it('moves a color that falls short only as far as it takes', () => {
    expect(contrastRatio('#6272a4', '#282a36')).toBeLessThan(AA)
    const moved = ensureContrast('#6272a4', ['#282a36'], AA)
    const ratio = contrastRatio(moved, '#282a36')
    // Just over the minimum: moved in small steps, and no further.
    expect(ratio).toBeGreaterThanOrEqual(AA)
    expect(ratio).toBeLessThan(AA + 0.3)
    // Darker over a light background.
    expect(
      contrastRatio(ensureContrast('#ffaa33', ['#ffffff'], 3), '#ffffff'),
    ).toBeGreaterThanOrEqual(3)
  })

  it.each(Object.keys(PALETTES))('«%s» gives every token of the app, as a color', (id) => {
    const colors = fromPalette(PALETTES[id as keyof typeof PALETTES])
    expect(Object.keys(colors).sort()).toEqual([...TOKEN_NAMES].sort())
    for (const value of Object.values(colors)) expect(value).toMatch(/^#[0-9a-f]{6}$/)
  })
})

describe('built-in themes (phase 22, CA8)', () => {
  it('there are at least 25, light and dark', () => {
    expect(BUILTIN_THEMES.length).toBeGreaterThanOrEqual(25)
    expect(BUILTIN_THEMES.map((t) => t.id)).toEqual([...BUILTIN_IDS])
    const light = BUILTIN_THEMES.filter((t) => t.base === 'light').length
    expect(light).toBeGreaterThanOrEqual(10)
    expect(BUILTIN_THEMES.length - light).toBeGreaterThanOrEqual(10)
  })

  it('every theme of another project has its credit, and only once', () => {
    const credited = THEME_CREDITS.flatMap((credit) => credit.themes)
    expect(new Set(credited).size).toBe(credited.length)
    expect([...credited, ...OWN_PALETTES].sort()).toEqual(Object.keys(PALETTES).sort())
    for (const credit of THEME_CREDITS) expect(credit.url).toMatch(/^https:\/\/github\.com\//)
  })

  it('the list the backend checks is up to date (generated/builtin-themes.json)', () => {
    expect(generated.ids).toEqual([...BUILTIN_IDS])
  })
})
