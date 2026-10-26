import { useQueryClient } from '@tanstack/react-query'
import { type Dispatch, type SetStateAction, useEffect } from 'react'
import { applyArchitectEvent, architectKeys, type ArchitectEvent } from '@/api/architect'
import { getApiBaseUrl } from '@/lib/api'

const MAX_BACKOFF_MS = 5000

/** WebSocket to one conversation's live events; reconnects with backoff until `close()`. */
export class ArchitectEventsSocket {
  private ws: WebSocket | null = null
  private closed = false
  private attempts = 0
  private timer: ReturnType<typeof setTimeout> | null = null

  private readonly conversationId: string
  private readonly onEvent: (event: ArchitectEvent) => void
  private readonly onConnection?: (connected: boolean) => void

  constructor(
    conversationId: string,
    onEvent: (event: ArchitectEvent) => void,
    onConnection?: (connected: boolean) => void,
  ) {
    this.conversationId = conversationId
    this.onEvent = onEvent
    this.onConnection = onConnection
  }

  async connect(): Promise<void> {
    if (this.closed) return
    const base = await getApiBaseUrl()
    if (this.closed) return
    const url = `${base.replace(/^http/, 'ws')}/api/architect/conversations/${this.conversationId}/events`
    const ws = new WebSocket(url)
    this.ws = ws
    ws.onopen = () => {
      this.attempts = 0
      this.onConnection?.(true)
    }
    ws.onmessage = (message) => {
      try {
        this.onEvent(JSON.parse(String(message.data)) as ArchitectEvent)
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

/** Follows a conversation live while it is shown: its messages, sheet and state go into the
 * query cache, and the blocks of the reply in progress to `setBlocks`. After a reconnection the
 * conversation is read again, because events were missed meanwhile. */
export function useArchitectEvents(
  conversationId: string | undefined,
  setBlocks: Dispatch<SetStateAction<string[]>>,
) {
  const queryClient = useQueryClient()
  useEffect(() => {
    if (!conversationId) return
    let first = true
    const socket = new ArchitectEventsSocket(
      conversationId,
      (event) => applyArchitectEvent(queryClient, conversationId, event, setBlocks),
      (connected) => {
        if (!connected) return
        if (!first)
          void queryClient.invalidateQueries({ queryKey: architectKeys.detail(conversationId) })
        first = false
      },
    )
    void socket.connect()
    return () => socket.close()
  }, [conversationId, queryClient, setBlocks])
}
