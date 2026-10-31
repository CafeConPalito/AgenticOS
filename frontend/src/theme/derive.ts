import { AA, AA_UI, contrastRatio } from './contrast'
import type { Base, TokenValues } from './model'

/**
 * Built-in themes from a short palette (phase 22, ADR 0028). The themes of other projects
 * (Dracula, Nord…) are written as their published colors, and every token of the app is
 * worked out from them by the same rules the navy and light sets follow. A color that falls
 * short of the app's contrast is moved, as little as it takes (`ensureContrast`).
 */
export interface Palette {
  base: Base
  background: string
  /** Cards. */
  surface: string
  /** Popovers and the top of cards. */
  raised: string
  border: string
  foreground: string
  /** Text of less weight. */
  muted: string
  /** The theme's color for actions, focus and the logo. */
  accent: string
  /** The side bar, dark in every theme: white text on it. */
  sidebar: string
  terminal: string
  terminalForeground: string
  /** The terminal's 16 colors: black, red, green, yellow, blue, magenta, cyan, white, then bright. */
  ansi: readonly string[]
}

const WHITE = '#ffffff'
const BLACK = '#000000'

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number]
}

function toHex(channels: number[]): string {
  return `#${channels
    .map((c) =>
      Math.round(Math.min(255, Math.max(0, c)))
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`
}

/** `a` moved towards `b` by `amount` (0 is `a`, 1 is `b`). */
export function mix(a: string, b: string, amount: number): string {
  const [x, y] = [rgb(a), rgb(b)]
  return toHex(x.map((c, i) => c + (y[i] - c) * amount))
}

/**
 * `color` as it is when it reads on every one of `backgrounds` with `ratio`; otherwise moved
 * step by step towards black or white (away from the backgrounds) until it does.
 */
export function ensureContrast(color: string, backgrounds: string[], ratio: number): string {
  const enough = (c: string) => backgrounds.every((b) => contrastRatio(c, b) >= ratio)
  if (enough(color)) return color
  // Towards the end with more room: white over dark backgrounds, black over light ones.
  const room = (end: string) => Math.min(...backgrounds.map((b) => contrastRatio(end, b)))
  const target = room(WHITE) >= room(BLACK) ? WHITE : BLACK
  for (let step = 1; step <= 50; step += 1) {
    const moved = mix(color, target, step / 50)
    if (enough(moved)) return moved
  }
  return target
}

/** Every token of the app from `p`. */
export function fromPalette(p: Palette): TokenValues {
  const dark = p.base === 'dark'
  const fg = ensureContrast(p.foreground, [p.background, p.surface], AA)
  const [black, red, green, yellow, blue, magenta, cyan, white] = p.ansi
  const bright = p.ansi.slice(8)
  // The vivid version of each hue: the bright ones read better on dark themes.
  const hue = (i: number) => (dark ? bright[i] : p.ansi[i])
  const onCard = (color: string) => ensureContrast(color, [p.surface], AA)
  const action = ensureContrast(p.accent, [WHITE], AA_UI + 0.2)
  const actionHover = ensureContrast(mix(action, dark ? WHITE : BLACK, 0.08), [WHITE], AA_UI)
  const destructive = ensureContrast(red, [WHITE], AA_UI + 0.2)
  const muted = mix(p.background, p.foreground, 0.05)
  const accent = mix(p.surface, p.accent, dark ? 0.2 : 0.12)
  const secondary = mix(p.surface, p.foreground, 0.06)
  const intervening = dark ? hue(3) : yellow
  return {
    background: p.background,
    foreground: fg,
    card: p.surface,
    'card-top': p.raised,
    'card-foreground': fg,
    popover: p.raised,
    'popover-foreground': ensureContrast(fg, [p.raised], AA),
    primary: dark ? mix(p.surface, p.foreground, 0.08) : p.sidebar,
    'primary-foreground': WHITE,
    'primary-action': action,
    'primary-action-hover': actionHover,
    secondary,
    'secondary-foreground': ensureContrast(fg, [secondary], AA),
    muted,
    'muted-foreground': ensureContrast(p.muted, [p.background, p.surface, muted], AA),
    accent,
    'accent-foreground': ensureContrast(fg, [accent], AA),
    destructive,
    'destructive-foreground': WHITE,
    border: p.border,
    input: mix(p.border, p.foreground, 0.12),
    ring: p.accent,
    subtle: mix(p.background, p.surface, 0.5),
    'graph-0': hue(4),
    'graph-1': hue(2),
    'graph-2': hue(1),
    'graph-3': hue(5),
    'graph-4': hue(6),
    'graph-5': hue(3),
    'graph-6': mix(hue(1), hue(5), 0.5),
    'graph-7': p.muted,
    sidebar: p.sidebar,
    'sidebar-foreground': WHITE,
    'sidebar-muted': ensureContrast(mix(p.sidebar, WHITE, 0.65), [p.sidebar], AA),
    'sidebar-primary': action,
    'sidebar-primary-foreground': WHITE,
    'sidebar-accent': mix(p.sidebar, WHITE, 0.1),
    'sidebar-accent-foreground': WHITE,
    'sidebar-border': mix(p.sidebar, WHITE, 0.06),
    'sidebar-ring': p.accent,
    terminal: p.terminal,
    'terminal-header': mix(p.terminal, BLACK, 0.15),
    'terminal-border': mix(p.terminal, p.terminalForeground, 0.12),
    'terminal-foreground': ensureContrast(p.terminalForeground, [p.terminal], AA),
    'terminal-muted': ensureContrast(mix(p.terminal, p.terminalForeground, 0.65), [p.terminal], AA),
    'terminal-accent': p.accent,
    'terminal-chip': mix(p.terminal, p.terminalForeground, 0.1),
    'terminal-dot': mix(p.terminal, p.terminalForeground, 0.2),
    'terminal-cursor': p.accent,
    'terminal-selection': mix(p.terminal, p.accent, 0.45),
    'ansi-black': black,
    'ansi-red': red,
    'ansi-green': green,
    'ansi-yellow': yellow,
    'ansi-blue': blue,
    'ansi-magenta': magenta,
    'ansi-cyan': cyan,
    'ansi-white': white,
    'ansi-bright-black': bright[0],
    'ansi-bright-red': bright[1],
    'ansi-bright-green': bright[2],
    'ansi-bright-yellow': bright[3],
    'ansi-bright-blue': bright[4],
    'ansi-bright-magenta': bright[5],
    'ansi-bright-cyan': bright[6],
    'ansi-bright-white': bright[7],
    'chart-1': hue(6),
    'chart-2': hue(5),
    'chart-3': hue(2),
    'chart-4': hue(1),
    'chart-5': hue(4),
    'status-queued': onCard(p.muted),
    'status-running': onCard(hue(6)),
    'status-waiting': onCard(hue(3)),
    'status-review': onCard(hue(5)),
    'status-done': onCard(hue(2)),
    'status-failed': onCard(hue(1)),
    'status-cancelled': onCard(mix(p.muted, p.surface, 0.2)),
    'status-intervening': intervening,
    'status-intervening-foreground': ensureContrast(
      contrastRatio(BLACK, intervening) >= contrastRatio(WHITE, intervening) ? '#1a1a1a' : WHITE,
      [intervening],
      AA_UI,
    ),
    'logo-from': p.accent,
    'logo-to': mix(p.accent, BLACK, 0.35),
    'logo-dot': hue(6),
  }
}
