import type { ITheme, Terminal } from '@xterm/xterm'
import { useEffect, useMemo, useRef } from 'react'
import type { TokenValues } from '@/theme/model'
import { useTheme } from '@/theme/ThemeProvider'

/** xterm.js colors from the theme's terminal tokens (phase 20). */
export function xtermTheme(c: TokenValues): ITheme {
  return {
    background: c.terminal,
    foreground: c['terminal-foreground'],
    cursor: c['terminal-cursor'],
    cursorAccent: c.terminal,
    selectionBackground: c['terminal-selection'],
    black: c['ansi-black'],
    red: c['ansi-red'],
    green: c['ansi-green'],
    yellow: c['ansi-yellow'],
    blue: c['ansi-blue'],
    magenta: c['ansi-magenta'],
    cyan: c['ansi-cyan'],
    white: c['ansi-white'],
    brightBlack: c['ansi-bright-black'],
    brightRed: c['ansi-bright-red'],
    brightGreen: c['ansi-bright-green'],
    brightYellow: c['ansi-bright-yellow'],
    brightBlue: c['ansi-bright-blue'],
    brightMagenta: c['ansi-bright-magenta'],
    brightCyan: c['ansi-bright-cyan'],
    brightWhite: c['ansi-bright-white'],
  }
}

/**
 * The terminal colors of the theme on screen, as a ref to create a terminal with, and kept
 * live on `termRef` when the theme changes (without recreating the terminal).
 */
export function useXtermTheme(termRef: React.RefObject<Terminal | null>) {
  const { resolved } = useTheme()
  const theme = useMemo(() => xtermTheme(resolved.colors), [resolved.colors])
  const current = useRef(theme)
  useEffect(() => {
    current.current = theme
    if (termRef.current) termRef.current.options.theme = theme
  }, [theme, termRef])
  return current
}
