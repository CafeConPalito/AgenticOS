import type { KnowledgeEvent } from '@/api/knowledge'
import { getApiBaseUrl } from '@/lib/api'

const MAX_BACKOFF_MS = 5000

/** WebSocket to the library's live events; reconnects with backoff until `close()`. */
export class KnowledgeEventsSocket {
  private ws: WebSocket | null = null
  private closed = false
  private attempts = 0
  private timer: ReturnType<typeof setTimeout> | null = null

  private readonly onEvent: (event: KnowledgeEvent) => void
  private readonly onConnection?: (connected: boolean) => void

  constructor(
    onEvent: (event: KnowledgeEvent) => void,
    onConnection?: (connected: boolean) => void,
  ) {
    this.onEvent = onEvent
    this.onConnection = onConnection
  }

  async connect(): Promise<void> {
    if (this.closed) return
    const base = await getApiBaseUrl()
    if (this.closed) return
    const ws = new WebSocket(`${base.replace(/^http/, 'ws')}/api/knowledge/events`)
    this.ws = ws
    ws.onopen = () => {
      this.attempts = 0
      this.onConnection?.(true)
    }
    ws.onmessage = (message) => {
      try {
        this.onEvent(JSON.parse(String(message.data)) as KnowledgeEvent)
      } catch {
        // an event this version does not understand
      }
    }
    ws.onclose = () => {
      this.onConnection?.(false)
      if (this.ws === ws) this.ws = null
      if (!this.closed) this.scheduleReconnect()
    }
  }

  private scheduleReconnect() {
    const delay = Math.min(250 * 2 ** this.attempts, MAX_BACKOFF_MS)
    this.attempts += 1
    this.timer = setTimeout(() => void this.connect(), delay)
  }

  close(): void {
    this.closed = true
    if (this.timer) clearTimeout(this.timer)
    this.ws?.close()
    this.ws = null
  }
}
