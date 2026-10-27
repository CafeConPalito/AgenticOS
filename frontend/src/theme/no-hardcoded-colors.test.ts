/**
 * CA9 (phase 20): the interface takes its colors from the theme tokens. A hex or rgb() color
 * in a component would not follow the theme. The only places allowed are `theme/` (the token
 * sets, the built-in themes and the data palettes), the tests and the fake backend.
 */
const sources = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

// Paths are relative to this folder: `./` is theme/ itself.
const ALLOWED = /^\.\/|^\.\.\/test\//
const COLOR = /#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![-\w])|\brgba?\(/

describe('no fixed colors outside the theme (phase 20, CA9)', () => {
  it('scans the sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(100)
  })

  it('finds none', () => {
    const found = Object.entries(sources)
      .filter(([path]) => !ALLOWED.test(path))
      .flatMap(([path, text]) =>
        text
          .split('\n')
          .map((line, i) => ({ path, line: i + 1, text: line.trim() }))
          .filter(({ text }) => COLOR.test(text)),
      )
    expect(found).toEqual([])
  })
})
