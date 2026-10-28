/**
 * The interface's errors and warnings, kept in the backend's log (phase 20) so the logs sent
 * with a bug report show what failed on screen too. A ring of the last BUFFER entries, sent at
 * most BATCH at a time every INTERVAL_MS; when the backend is away they are dropped (its own
 * log tells that story).
 */
const BUFFER = 200
const BATCH = 50
const INTERVAL_MS = 5000
const MAX_MESSAGE = 2000

interface Entry {
  level: 'error' | 'warn'
  message: string
  source: string
  at: string
}

const pending: Entry[] = []
let timer: ReturnType<typeof setTimeout> | null = null
let sending = false

export function recordClientLog(level: Entry['level'], message: unknown, source = '') {
  // A failure while sending must not log itself again.
  if (sending) return
  pending.push({
    level,
    message: describe(message).slice(0, MAX_MESSAGE),
    source: source.slice(0, 300),
    at: new Date().toISOString(),
  })
  if (pending.length > BUFFER) pending.splice(0, pending.length - BUFFER)
  timer ??= setTimeout(() => void flush(), INTERVAL_MS)
}

export async function flush() {
  timer = null
  const entries = pending.splice(0, BATCH)
  if (entries.length === 0) return
  sending = true
  try {
    // Loaded here, not at the top: the test setup imports this module before the tests mock
    // what `lib/api` depends on.
    const { api } = await import('@/lib/api')
    await api.post('/api/support/client-log', { entries })
  } catch {
    // The backend is away: these are dropped.
  } finally {
    sending = false
  }
  if (pending.length > 0) timer ??= setTimeout(() => void flush(), INTERVAL_MS)
}

function describe(value: unknown): string {
  if (value instanceof Error) return `${value.name}: ${value.message}`
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

let installed = false

/** Uncaught errors, rejected promises and `console.error`/`console.warn`, from now on. */
export function installClientLog() {
  if (installed) return
  installed = true
  window.addEventListener('error', (event) =>
    recordClientLog('error', event.error ?? event.message, `${event.filename}:${event.lineno}`),
  )
  window.addEventListener('unhandledrejection', (event) =>
    recordClientLog('error', event.reason, 'unhandledrejection'),
  )
  for (const level of ['error', 'warn'] as const) {
    const original = console[level].bind(console)
    console[level] = (...args: unknown[]) => {
      original(...args)
      recordClientLog(level, args.map(describe).join(' '), 'console')
    }
  }
}

/** For tests. */
export function pendingClientLog(): readonly Entry[] {
  return pending
}

/** For tests: nothing pending, nothing scheduled. */
export function resetClientLog() {
  if (timer) clearTimeout(timer)
  timer = null
  sending = false
  pending.length = 0
}
