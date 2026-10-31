import { isTauri } from '@tauri-apps/api/core'
import type { Density, Font, ResolvedTheme } from './model'
import { syncTitlebar } from './titlebar'

/** The CSS variables of the last theme applied, for `index.html` to paint before React. */
export const APPLIED_KEY = 'agentic-os.theme.applied'

export const FONT_STACKS: Record<Font, string> = {
  ubuntu: "'Ubuntu', ui-sans-serif, system-ui, sans-serif",
  inter: "'Inter', ui-sans-serif, system-ui, sans-serif",
  atkinson: "'Atkinson Hyperlegible', ui-sans-serif, system-ui, sans-serif",
  system: "system-ui, 'Segoe UI', sans-serif",
}

/** Tailwind v4 derives every margin, padding and gap from `--spacing`. */
const SPACING: Record<Density, string> = {
  compact: '0.22rem',
  normal: '0.25rem',
  comfortable: '0.28rem',
}

/** A font of the system first, then the system's own (what a missing font falls back to). */
export function fontStack(theme: Pick<ResolvedTheme, 'font' | 'fontFamily'>): string {
  // FONT_FAMILY lets no quote or backslash through; escaped all the same.
  if (theme.fontFamily) return `"${theme.fontFamily.replace(/["\\]/g, '')}", ${FONT_STACKS.system}`
  return FONT_STACKS[theme.font]
}

export function cssVariables(theme: ResolvedTheme): Record<string, string> {
  const vars: Record<string, string> = {}
  for (const [name, value] of Object.entries(theme.colors)) vars[`--${name}`] = value
  vars['--app-font'] = fontStack(theme)
  vars['--spacing'] = SPACING[theme.density]
  vars['--radius'] = `${theme.radius / 16}rem`
  return vars
}

let appliedZoom = 1

/**
 * Paints `theme` on the whole app: the CSS variables on `<html>`, the `.dark` class that the
 * Tailwind `dark:` variants follow, and the text scale as the webview's zoom (CSS zoom would
 * break the `100vh` layouts). In a plain browser the scale is the browser's own zoom.
 */
export function applyTheme(theme: ResolvedTheme, root: HTMLElement = document.documentElement) {
  const vars = cssVariables(theme)
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value)
  root.classList.toggle('dark', theme.base === 'dark')
  root.style.colorScheme = theme.base
  try {
    localStorage.setItem(APPLIED_KEY, JSON.stringify({ base: theme.base, vars }))
  } catch {
    // Storage unavailable: the next start paints the default theme first.
  }
  syncTitlebar(theme)
  if (theme.scale !== appliedZoom && isTauri()) {
    appliedZoom = theme.scale
    void import('@tauri-apps/api/webview')
      .then(({ getCurrentWebview }) => getCurrentWebview().setZoom(theme.scale))
      .catch(() => {})
  }
}
