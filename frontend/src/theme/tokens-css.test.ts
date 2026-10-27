/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { BASE_TOKENS, TOKEN_NAMES } from './model'

/** The `--name: #value;` declarations of one top-level block of tokens.css. */
function block(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`)
  const body = css.slice(start, css.indexOf('\n}', start))
  return Object.fromEntries(
    [...body.matchAll(/^\s+--([a-z0-9-]+):\s*(#[0-9a-f]{6,8});/gim)].map((m) => [
      m[1],
      m[2].toLowerCase(),
    ]),
  )
}

describe('tokens.css and the base token sets (phase 20)', () => {
  // Vitest runs with `css: false`, which empties CSS imports (even `?raw`): read the file.
  const css = readFileSync(`${process.cwd()}/src/styles/tokens.css`, 'utf8')
  const light = block(css, ':root')
  const dark = { ...light, ...block(css, '.dark') }

  it.each(TOKEN_NAMES)(
    '«%s» has the same value in the CSS and in the light and navy sets',
    (name) => {
      expect(light[name], `:root --${name}`).toBe(BASE_TOKENS.light[name])
      expect(dark[name], `.dark --${name}`).toBe(BASE_TOKENS.dark[name])
    },
  )
})
