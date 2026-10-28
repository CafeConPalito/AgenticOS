import { invoke, isTauri } from '@tauri-apps/api/core'
import type { ResolvedTheme } from './model'

let last = ''

/**
 * Paints the window's title bar with the theme (phase 20, amendment 1): the page background
 * and its text, and the base for the system's dark or light bar. The shell decides what the
 * system can do with it (Windows 11 colors, Windows 10 dark or light, nothing elsewhere).
 */
export function syncTitlebar(theme: ResolvedTheme) {
  if (!isTauri()) return
  const args = {
    background: theme.colors.background,
    foreground: theme.colors.foreground,
    dark: theme.base === 'dark',
  }
  const key = JSON.stringify(args)
  if (key === last) return
  last = key
  invoke('set_titlebar', args).catch(() => {
    // An old shell without the command, or a system without title bar colors.
    last = ''
  })
}

/** For tests: forget what was painted last. */
export function resetTitlebar() {
  last = ''
}
