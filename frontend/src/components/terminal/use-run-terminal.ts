import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { runKeys } from '@/api/runs'
import type { Run, RunStatus } from '@/api/types'
import { newViewerId } from '@/lib/client-id'
import { TerminalSocket, type TerminalState } from '@/lib/terminal-socket'

/** xterm theme aligned with the design tokens (the terminal is always dark). */
export const XTERM_THEME = {
  background: '#050E1E',
  foreground: '#D7E1F0',
  cursor: '#4CC9F0',
  cursorAccent: '#050E1E',
  selectionBackground: '#2E5BD6',
  black: '#0A1A33',
  brightBlack: '#7F8DAA',
  red: '#FF6B6F',
  green: '#43D392',
  yellow: '#F5B547',
  blue: '#8FB4FF',
  magenta: '#B39CFF',
  cyan: '#4CC9F0',
  white: '#D7E1F0',
  brightWhite: '#FFFFFF',
}

export interface RunTerminal {
  containerRef: React.RefObject<HTMLDivElement | null>
  viewerId: string
  state: TerminalState | null
  exit: { code: number | null; status: RunStatus } | null
  connected: boolean
  /** This view holds the control (it can type). */
  interactive: boolean
}

/**
 * Mounts an xterm.js terminal bound to a run's WebSocket. Keystrokes are only sent while this
 * view holds the control; the backend enforces it as well.
 */
export function useRunTerminal(runId: string): RunTerminal {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const queryClient = useQueryClient()
  const [viewerId] = useState(newViewerId)
  const [state, setState] = useState<TerminalState | null>(null)
  const [exit, setExit] = useState<RunTerminal['exit']>(null)
  const [connected, setConnected] = useState(false)
  const termRef = useRef<Terminal | null>(null)
  const socketRef = useRef<TerminalSocket | null>(null)
  const interactive = state?.controller === viewerId
  const interactiveRef = useRef(interactive)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const term = new Terminal({
      theme: XTERM_THEME,
      fontFamily: "'Ubuntu Mono', ui-monospace, monospace",
      fontSize: 13,
      lineHeight: 1.2,
      scrollback: 10000,
      cursorBlink: true,
      disableStdin: !interactiveRef.current,
      allowProposedApi: false,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(container)
    termRef.current = term

    const socket = new TerminalSocket(runId, viewerId, {
      onSnapshot: (data) => {
        term.reset()
        term.write(data)
      },
      onOutput: (data) => term.write(data),
      onState: (next) => {
        setState(next)
        // Live status for everything else showing this run (header, lists).
        queryClient.setQueryData<Run>(runKeys.detail(runId), (run) => run && { ...run, ...next })
      },
      onExit: (code, status) => {
        setExit({ code, status })
        void queryClient.invalidateQueries({ queryKey: runKeys.all })
      },
      onConnection: setConnected,
    })
    socketRef.current = socket
    void socket.connect()

    const inputSub = term.onData((data) => {
      if (interactiveRef.current) socket.sendInput(data)
    })

    let resizeTimer: ReturnType<typeof setTimeout> | undefined
    const refit = () => {
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => {
        try {
          fit.fit()
          socket.sendResize(term.cols, term.rows)
        } catch {
          // container hidden (e.g. collapsed dock): nothing to fit
        }
      }, 80)
    }
    const observer = new ResizeObserver(refit)
    observer.observe(container)
    refit()

    return () => {
      clearTimeout(resizeTimer)
      observer.disconnect()
      inputSub.dispose()
      socket.close()
      term.dispose()
      termRef.current = null
      socketRef.current = null
    }
  }, [runId, viewerId, queryClient])

  useEffect(() => {
    interactiveRef.current = interactive
    const term = termRef.current
    if (!term) return
    term.options.disableStdin = !interactive
    if (interactive) {
      term.focus()
      // The view holding the control decides the terminal size.
      socketRef.current?.sendResize(term.cols, term.rows)
    }
  }, [interactive])

  return { containerRef, viewerId, state, exit, connected, interactive }
}
