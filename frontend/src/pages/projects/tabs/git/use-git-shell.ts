import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useRef, useState } from 'react'
import { useXtermTheme } from '@/components/terminal/xterm-theme'
import { newViewerId } from '@/lib/client-id'
import { TerminalSocket } from '@/lib/terminal-socket'

/** Mounts the terminal of a git shell (a terminal in the repository's folder). Always
 * interactive and fitted to its container; `exited` turns true when the shell ends. */
export function useGitShell(shellId: string) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [viewerId] = useState(newViewerId)
  const [exited, setExited] = useState(false)
  const [connected, setConnected] = useState(false)
  const termRef = useRef<Terminal | null>(null)
  const xtermTheme = useXtermTheme(termRef)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    setExited(false)
    const term = new Terminal({
      theme: xtermTheme.current,
      fontFamily: "'Ubuntu Mono', ui-monospace, monospace",
      fontSize: 13,
      lineHeight: 1.2,
      scrollback: 5000,
      cursorBlink: true,
      allowProposedApi: false,
    })
    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    term.loadAddon(new WebLinksAddon())
    term.open(container)
    termRef.current = term

    const socket = new TerminalSocket(
      shellId,
      viewerId,
      {
        onSnapshot: (data) => {
          term.reset()
          term.write(data)
        },
        onOutput: (data) => term.write(data),
        onState: () => {},
        onExit: () => setExited(true),
        onConnection: setConnected,
      },
      `/api/git/shells/${shellId}/terminal`,
    )
    void socket.connect()
    const input = term.onData((data) => socket.sendInput(data))

    let timer: ReturnType<typeof setTimeout> | undefined
    const refit = () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        try {
          fitAddon.fit()
          socket.sendResize(term.cols, term.rows)
        } catch {
          // not laid out yet: nothing to fit
        }
      }, 80)
    }
    const observer = new ResizeObserver(refit)
    observer.observe(container)
    refit()
    term.focus()

    return () => {
      clearTimeout(timer)
      observer.disconnect()
      input.dispose()
      socket.close()
      term.dispose()
      termRef.current = null
    }
  }, [shellId, viewerId, xtermTheme])

  return { containerRef, exited, connected }
}
