import { saveFile } from '@/lib/save-file'
import { BUILTIN_IDS } from '@/theme/builtin'
import { type Appearance, type ThemeDefinition, themeSchema, type TokenName } from '@/theme/model'

/** The editor's groups of tokens, in order (phase 20, block 4). */
export const TOKEN_GROUPS = [
  {
    id: 'surfaces',
    tokens: ['background', 'card', 'card-top', 'popover', 'subtle', 'muted', 'border', 'input'],
  },
  {
    id: 'text',
    tokens: ['foreground', 'card-foreground', 'popover-foreground', 'muted-foreground'],
  },
  {
    id: 'action',
    tokens: [
      'primary',
      'primary-foreground',
      'primary-action',
      'primary-action-hover',
      'secondary',
      'secondary-foreground',
      'accent',
      'accent-foreground',
      'ring',
      'destructive',
      'destructive-foreground',
    ],
  },
  {
    id: 'status',
    tokens: [
      'status-queued',
      'status-running',
      'status-waiting',
      'status-review',
      'status-done',
      'status-failed',
      'status-cancelled',
      'status-intervening',
      'status-intervening-foreground',
    ],
  },
  {
    id: 'sidebar',
    tokens: [
      'sidebar',
      'sidebar-foreground',
      'sidebar-muted',
      'sidebar-primary',
      'sidebar-accent',
      'sidebar-border',
    ],
  },
  {
    id: 'terminal',
    tokens: [
      'terminal',
      'terminal-header',
      'terminal-border',
      'terminal-foreground',
      'terminal-muted',
      'terminal-accent',
      'terminal-chip',
      'terminal-dot',
      'terminal-cursor',
      'terminal-selection',
      'ansi-black',
      'ansi-red',
      'ansi-green',
      'ansi-yellow',
      'ansi-blue',
      'ansi-magenta',
      'ansi-cyan',
      'ansi-white',
      'ansi-bright-black',
      'ansi-bright-red',
      'ansi-bright-green',
      'ansi-bright-yellow',
      'ansi-bright-blue',
      'ansi-bright-magenta',
      'ansi-bright-cyan',
      'ansi-bright-white',
    ],
  },
  {
    id: 'charts',
    tokens: [
      'chart-1',
      'chart-2',
      'chart-3',
      'chart-4',
      'chart-5',
      'graph-0',
      'graph-1',
      'graph-2',
      'graph-3',
      'graph-4',
      'graph-5',
      'graph-6',
      'graph-7',
    ],
  },
  { id: 'brand', tokens: ['logo-from', 'logo-to', 'logo-dot'] },
] as const satisfies readonly { id: string; tokens: readonly TokenName[] }[]

/** A free id from a name: «Mi tema» → `mi-tema`, then `mi-tema-2`… */
export function freeId(name: string, taken: Iterable<string>): string {
  const used = new Set<string>([...BUILTIN_IDS, ...taken])
  const base =
    name
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 32) || 'tema'
  let id = base
  for (let n = 2; used.has(id); n += 1) id = `${base}-${n}`
  return id
}

/** Saves a theme as `<id>.theme.json`: the path, null if cancelled (see `saveFile`). */
export function downloadTheme(theme: ThemeDefinition) {
  return saveFile({
    name: `${theme.id}.theme.json`,
    text: JSON.stringify(theme, null, 2),
    type: 'application/json',
    filter: 'Tema',
    extensions: ['json'],
  })
}

export type ImportResult =
  | { ok: true; theme: ThemeDefinition; renamed: boolean }
  | { ok: false; reason: 'json' | 'field' | 'extends'; field?: string }

/**
 * Reads an exported theme. A broken file, a value out of place or a theme it extends that
 * this installation lacks are refused with the reason; a clashing id gets a new one.
 */
export function parseTheme(text: string, appearance: Appearance): ImportResult {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { ok: false, reason: 'json' }
  }
  const parsed = themeSchema.safeParse(data)
  if (!parsed.success) {
    const issue = parsed.error.issues[0]
    return { ok: false, reason: 'field', field: issue.path.join('.') || issue.message }
  }
  const theme = parsed.data
  const ids = appearance.custom.map((c) => c.id)
  if (![...(BUILTIN_IDS as readonly string[]), ...ids].includes(theme.extends))
    return { ok: false, reason: 'extends', field: theme.extends }
  const id = freeId(theme.id, ids)
  return { ok: true, theme: { ...theme, id }, renamed: id !== theme.id }
}

/** The appearance without `id`: whatever used it goes back to the built-in light or navy. */
export function withoutTheme(appearance: Appearance, id: string): Appearance {
  const replace = (current: string, fallback: string) => (current === id ? fallback : current)
  return {
    ...appearance,
    theme: replace(appearance.theme, 'navy'),
    light_theme: replace(appearance.light_theme, 'light'),
    dark_theme: replace(appearance.dark_theme, 'navy'),
    // Themes that extended it now extend what it extended.
    custom: appearance.custom
      .filter((c) => c.id !== id)
      .map((c) =>
        c.extends === id
          ? { ...c, extends: appearance.custom.find((x) => x.id === id)?.extends ?? 'navy' }
          : c,
      ),
  }
}
