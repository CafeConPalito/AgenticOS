import { BUILTIN_IDS } from './builtin'
import { contrastIssues, contrastRatio, readableOn } from './contrast'
import { resolveTheme } from './resolve'

describe('contrast (phase 20, CA8)', () => {
  it('computes the WCAG ratio', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1)
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5)
    expect(contrastRatio('#767676', '#ffffff')).toBeCloseTo(4.54, 2)
  })

  it.each(BUILTIN_IDS)('the built-in theme «%s» passes every pair', (id) => {
    expect(contrastIssues(resolveTheme(id, []).colors)).toEqual([])
  })

  it('reports the pairs under AA, worst first', () => {
    const colors = { ...resolveTheme('light', []).colors, 'muted-foreground': '#c0c0c0' }
    const issues = contrastIssues(colors)
    expect(issues.map((i) => `${i.text}/${i.background}`)).toEqual([
      'muted-foreground/background',
      'muted-foreground/card',
    ])
  })

  it('picks dark ink or white for text on a color', () => {
    expect(readableOn('#8fb4ff')).toBe('#0a1a33')
    expect(readableOn('#13284d')).toBe('#ffffff')
    expect(readableOn('var(--x)')).toBe('#0a1a33')
  })
})
