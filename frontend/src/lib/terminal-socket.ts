import type { RunActivity, RunEvent, RunStatus } from '@/api/types'
import { getApiBaseUrl } from '@/lib/api'

export interface TerminalState {
  status: RunStatus
  activity: RunActivity
  controller: string | null
  /** PTY size, set by the view that sizes the terminal. */
  cols: number
  rows: number
}

export type ServerMessage =
  | { type: 'snapshot'; data: string }
  | { type: 'output'; data: string }
  | ({ type: 'state' } & TerminalState)
  | { type: 'exit'; code: number | null; status: RunStatus }
  | ({ type: 'event' } & RunEvent)

export interface TerminalSocketHandlers {
  onSnapshot: (data: string) => void
  onOutput: (data: string) => void
  onState: (state: TerminalState) => void
  onExit: (code: number | null, status: RunStatus) => void
  onEvent?: (event: RunEvent) => void
  onConnection?: (connected: boolean) => void
}

const MAX_BACKOFF_MS = 5000

/**
 * WebSocket to a run's terminal. Reconnects with backoff until the run exits or `close()`
 * is called; every (re)connection starts with a snapshot of the scrollback.
 */
export class TerminalSocket {
  private ws: WebSocket | null = null
  private closed = false
  private exited = false
  private attempts = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private readonly runId: string
  private readonly viewerId: string
  private readonly handlers: TerminalSocketHandlers

  constructor(runId: string, viewerId: string, handlers: TerminalSocketHandlers) {
    this.runId = runId
    this.viewerId = viewerId
    this.handlers = handlers
  }

  async connect(): Promise<void> {
    if (this.closed) return
    const base = await getApiBaseUrl()
    if (this.closed) return
    const url = `${base.replace(/^http/, 'ws')}/api/runs/${this.runId}/terminal?client_id=${encodeURIComponent(this.viewerId)}`
    const ws = new WebSocket(url)
    this.ws = ws
    ws.onopen = () => {
      this.attempts = 0
      this.handlers.onConnection?.(true)
    }
    ws.onmessage = (event) => this.dispatch(JSON.parse(String(event.data)) as ServerMessage)
    ws.onclose = () => {
      this.handlers.onConnection?.(false)
      if (this.ws === ws) this.ws = null
      if (!this.closed && !this.exited) this.scheduleReconnect()
    }
  }

  private dispatch(message: ServerMessage) {
    switch (message.type) {
      case 'snapshot':
        this.handlers.onSnapshot(message.data)
        break
      case 'output':
        this.handlers.onOutput(message.data)
        break
      case 'state':
        this.handlers.onState({
          status: message.status,
          activity: message.activity,
          controller: message.controller,
          cols: message.cols,
          rows: message.rows,
        })
        break
      case 'exit':
        this.exited = true
        this.handlers.onExit(message.code, message.status)
        break
      case 'event':
        this.handlers.onEvent?.({
          id: message.id,
          run_id: message.run_id,
          at: message.at,
          kind: message.kind,
          name: message.name,
          detail: message.detail,
        })
        break
    }
  }

  private scheduleReconnect() {
    this.attempts += 1
    const delay = Math.min(MAX_BACKOFF_MS, 250 * 2 ** (this.attempts - 1))
    this.timer = setTimeout(() => void this.connect(), delay)
  }

  private send(message: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message))
  }

  sendInput(data: string) {
    this.send({ type: 'input', data })
  }

  sendResize(cols: number, rows: number) {
    this.send({ type: 'resize', cols, rows })
  }

  close() {
    this.closed = true
    if (this.timer) clearTimeout(this.timer)
    this.ws?.close()
    this.ws = null
  }
}
