import { z } from 'zod'

/**
 * Themes as data (phase 20, ADR 0027). A theme is a set of values for the CSS tokens of
 * `styles/tokens.css`, plus the font, the text scale, the density and the corner radius.
 * The two base token sets below are the light (`:root`) and navy (`.dark`) blocks of
 * tokens.css; a test keeps both in step.
 */

const LIGHT = {
  background: '#f4f6fa',
  foreground: '#0a1a33',
  card: '#ffffff',
  'card-top': '#ffffff',
  'card-foreground': '#0a1a33',
  popover: '#ffffff',
  'popover-foreground': '#0a1a33',
  primary: '#13284d',
  'primary-foreground': '#ffffff',
  'primary-action': '#1b3f8f',
  'primary-action-hover': '#24499f',
  secondary: '#e9eef6',
  'secondary-foreground': '#0a1a33',
  muted: '#eef2f8',
  'muted-foreground': '#4b5b78',
  accent: '#e3eaf5',
  'accent-foreground': '#0a1a33',
  destructive: '#c9302c',
  'destructive-foreground': '#ffffff',
  border: '#d6deea',
  input: '#c9d3e3',
  ring: '#2e5bd6',
  subtle: '#f8fafd',
  'graph-0': '#3b6bdc',
  'graph-1': '#1f9d6b',
  'graph-2': '#c2410c',
  'graph-3': '#8b5cf6',
  'graph-4': '#0e8aa6',
  'graph-5': '#b45309',
  'graph-6': '#be185d',
  'graph-7': '#5b6b86',
  sidebar: '#0f2347',
  'sidebar-foreground': '#ffffff',
  'sidebar-muted': '#aebcd6',
  'sidebar-primary': '#2e5bd6',
  'sidebar-primary-foreground': '#ffffff',
  'sidebar-accent': '#1f3c6e',
  'sidebar-accent-foreground': '#ffffff',
  'sidebar-border': '#1a3360',
  'sidebar-ring': '#7aa2ff',
  terminal: '#0a1a33',
  'terminal-header': '#081429',
  'terminal-border': '#16294a',
  'terminal-foreground': '#d7e1f0',
  'terminal-muted': '#9aa9c4',
  'terminal-accent': '#4cc9f0',
  'terminal-chip': '#13284d',
  'terminal-dot': '#1e3a66',
  'terminal-cursor': '#4cc9f0',
  'terminal-selection': '#2e5bd6',
  'ansi-black': '#0a1a33',
  'ansi-red': '#ff6b6f',
  'ansi-green': '#43d392',
  'ansi-yellow': '#f5b547',
  'ansi-blue': '#8fb4ff',
  'ansi-magenta': '#b39cff',
  'ansi-cyan': '#4cc9f0',
  'ansi-white': '#d7e1f0',
  'ansi-bright-black': '#7f8daa',
  'ansi-bright-red': '#ef2929',
  'ansi-bright-green': '#8ae234',
  'ansi-bright-yellow': '#fce94f',
  'ansi-bright-blue': '#729fcf',
  'ansi-bright-magenta': '#ad7fa8',
  'ansi-bright-cyan': '#34e2e2',
  'ansi-bright-white': '#ffffff',
  'chart-1': '#0a78a3',
  'chart-2': '#c2477f',
  'chart-3': '#5e8a1a',
  'chart-4': '#c2621f',
  'chart-5': '#6a4fd1',
  'status-queued': '#4f6385',
  'status-running': '#0a78a3',
  'status-waiting': '#9a6200',
  'status-review': '#6a4fd1',
  'status-done': '#12805a',
  'status-failed': '#c9302c',
  'status-cancelled': '#647089',
  'status-intervening': '#f5b547',
  'status-intervening-foreground': '#0a1a33',
  'logo-from': '#3b69e8',
  'logo-to': '#1b3f8f',
  'logo-dot': '#4cc9f0',
} as const

export type TokenName = keyof typeof LIGHT
export type TokenValues = Record<TokenName, string>

const NAVY: TokenValues = {
  ...LIGHT,
  background: '#0a1a33',
  foreground: '#ffffff',
  card: '#0f2242',
  'card-top': '#13294b',
  'card-foreground': '#ffffff',
  popover: '#13284d',
  'popover-foreground': '#ffffff',
  'primary-action': '#2e5bd6',
  'primary-action-hover': '#3b69e8',
  secondary: '#16305a',
  'secondary-foreground': '#ffffff',
  muted: '#122a4e',
  'muted-foreground': '#a8b6cf',
  accent: '#1a3562',
  'accent-foreground': '#ffffff',
  destructive: '#e5484d',
  border: '#1e3a66',
  input: '#24426f',
  ring: '#7aa2ff',
  subtle: '#0c1d38',
  'graph-0': '#7ea2ff',
  'graph-1': '#43d392',
  'graph-2': '#ff9a62',
  'graph-3': '#b39cff',
  'graph-4': '#4cc9f0',
  'graph-5': '#f5b547',
  'graph-6': '#ff7eb6',
  'graph-7': '#9aa8c2',
  sidebar: '#071427',
  'sidebar-muted': '#9aa9c4',
  'sidebar-accent': '#16305a',
  'sidebar-border': '#13284a',
  terminal: '#050e1e',
  'chart-1': '#4cc9f0',
  'chart-2': '#f27fb2',
  'chart-3': '#b5e061',
  'chart-4': '#ffa06b',
  'chart-5': '#b39cff',
  'status-queued': '#9db0d0',
  'status-running': '#4cc9f0',
  'status-waiting': '#f5b547',
  'status-review': '#b39cff',
  'status-done': '#43d392',
  'status-failed': '#ff6b6f',
  'status-cancelled': '#8492ae',
}

export type Base = 'light' | 'dark'
export const BASE_TOKENS: Record<Base, TokenValues> = { light: LIGHT, dark: NAVY }
export const TOKEN_NAMES = Object.keys(LIGHT) as TokenName[]

export const FONTS = ['ubuntu', 'inter', 'atkinson', 'system'] as const
export type Font = (typeof FONTS)[number]
export const DENSITIES = ['compact', 'normal', 'comfortable'] as const
export type Density = (typeof DENSITIES)[number]

export const DEFAULTS = { font: 'ubuntu', scale: 1, density: 'normal', radius: 10 } as const

const themeId = z.string().regex(/^[a-z0-9][a-z0-9-]{0,39}$/)
const hex = z.string().regex(/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/)
/** A font installed on the system (ADR 0028): safe to write quoted in a CSS font-family. */
export const FONT_FAMILY = /^[\p{L}\p{N}][\p{L}\p{N} ._'&()+-]{0,79}$/u

/**
 * `agentic-os.theme` v2 (ADR 0028), as the backend stores it and as it is exported. It reads
 * v1 too: v2 only adds themes made from scratch (no `extends`) and `font_family`.
 */
export const themeSchema = z
  .object({
    format: z.literal('agentic-os.theme').default('agentic-os.theme'),
    version: z.union([z.literal(1), z.literal(2)]).default(2),
    id: themeId,
    name: z.string().trim().min(1).max(60),
    base: z.enum(['light', 'dark']),
    extends: themeId.nullish(),
    colors: z.partialRecord(z.enum(TOKEN_NAMES as [TokenName, ...TokenName[]]), hex).default({}),
    font: z.enum(FONTS).nullish(),
    /** Over `font` when set. */
    font_family: z.string().regex(FONT_FAMILY).nullish(),
    scale: z.number().min(0.8).max(1.5).nullish(),
    density: z.enum(DENSITIES).nullish(),
    radius: z.number().int().min(0).max(20).nullish(),
  })
  .strict()

export type ThemeDefinition = z.infer<typeof themeSchema>

export interface Appearance {
  theme: string
  custom: ThemeDefinition[]
}

/** «Seguir al sistema» of a phase 20 document, gone in phase 22: only ever read (ADR 0028). */
export interface LegacyFollow {
  light_theme: string
  dark_theme: string
}

export const DEFAULT_APPEARANCE: Appearance = { theme: 'navy', custom: [] }

/** A theme fully worked out: every token has a value. */
export interface ResolvedTheme {
  id: string
  base: Base
  colors: TokenValues
  font: Font
  /** A font of the system, over `font`. */
  fontFamily: string | null
  scale: number
  density: Density
  radius: number
}
