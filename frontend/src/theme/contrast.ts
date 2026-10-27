import type { TokenName, TokenValues } from './model'

/** WCAG 2.x relative luminance of a `#rrggbb` color. */
export function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)
}

/** Contrast ratio between two `#rrggbb` colors, from 1 to 21. */
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

export const AA = 4.5
/** Bold button labels on an action color: WCAG's 3:1 for user interface components. */
export const AA_UI = 3

/** Text over background pairs that must be readable, with their minimum ratio. */
export const CONTRAST_PAIRS: [TokenName, TokenName, number?][] = [
  ['foreground', 'background'],
  ['card-foreground', 'card'],
  ['popover-foreground', 'popover'],
  ['muted-foreground', 'background'],
  ['muted-foreground', 'card'],
  ['primary-foreground', 'primary-action', AA_UI],
  ['primary-foreground', 'primary-action-hover', AA_UI],
  ['accent-foreground', 'accent'],
  ['secondary-foreground', 'secondary'],
  ['destructive-foreground', 'destructive', AA_UI],
  ['status-queued', 'card'],
  ['status-running', 'card'],
  ['status-waiting', 'card'],
  ['status-review', 'card'],
  ['status-done', 'card'],
  ['status-failed', 'card'],
  ['status-cancelled', 'card'],
  ['status-intervening-foreground', 'status-intervening', AA_UI],
  ['terminal-foreground', 'terminal'],
  ['terminal-muted', 'terminal'],
]

export interface ContrastIssue {
  text: TokenName
  background: TokenName
  ratio: number
  minimum: number
}

/** The pairs of a theme under their minimum, worst first. */
export function contrastIssues(colors: TokenValues): ContrastIssue[] {
  return CONTRAST_PAIRS.map(([text, background, minimum = AA]) => ({
    text,
    background,
    minimum,
    ratio: contrastRatio(colors[text].slice(0, 7), colors[background].slice(0, 7)),
  }))
    .filter((issue) => issue.ratio < issue.minimum)
    .sort((a, b) => a.ratio - b.ratio)
}

/** Dark ink or white, whichever reads better on `hex` (agent avatars, chips). */
export function readableOn(hex: string, dark = '#0a1a33', light = '#ffffff'): string {
  if (!/^#[0-9a-fA-F]{6}/.test(hex)) return dark
  return contrastRatio(hex.slice(0, 7), dark) >= contrastRatio(hex.slice(0, 7), light)
    ? dark
    : light
}
