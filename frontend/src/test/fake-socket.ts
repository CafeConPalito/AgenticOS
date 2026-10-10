import type { ServerMessage } from '@/lib/terminal-socket'

/** WebSocket stand-in: records what the client sends and lets tests push server messages. */
export class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = FakeWebSocket.CONNECTING
  sent: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  /** Accepts the connection and sends the opening messages, like the backend does. */
  open(...messages: ServerMessage[]) {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
    messages.forEach((m) => this.push(m))
  }

  push(message: ServerMessage) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  send(data: string) {
    this.sent.push(JSON.parse(data))
  }

  close() {
    if (this.readyState === FakeWebSocket.CLOSED) return
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }

  get viewerId(): string {
    return new URL(this.url).searchParams.get('client_id') ?? ''
  }
}

export function installFakeWebSocket() {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  return FakeWebSocket
}
