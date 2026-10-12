import { invoke, isTauri } from '@tauri-apps/api/core'

export const DEFAULT_API_URL = 'http://127.0.0.1:8765'

const TAURI_RETRIES = 120
const TAURI_RETRY_DELAY_MS = 250
/** Error the Tauri shell returns while the sidecar boots; any other error is final. */
export const BACKEND_STARTING = 'starting'

let baseUrlPromise: Promise<string> | null = null

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const toError = (error: unknown) => (error instanceof Error ? error : new Error(String(error)))

/** Asks the Tauri shell for the sidecar URL, retrying only while the backend is starting. */
async function resolveTauriUrl(): Promise<string> {
  for (let attempt = 0; attempt < TAURI_RETRIES; attempt++) {
    try {
      return await invoke<string>('backend_url')
    } catch (error) {
      if (error !== BACKEND_STARTING) throw toError(error)
      await sleep(TAURI_RETRY_DELAY_MS)
    }
  }
  throw new Error('backend did not start in time')
}

/** Base URL of the backend: Tauri sidecar in the desktop app, env/default in the browser. */
export function getApiBaseUrl(): Promise<string> {
  if (!baseUrlPromise) {
    baseUrlPromise = isTauri()
      ? resolveTauriUrl().catch((error: unknown) => {
          baseUrlPromise = null
          throw error
        })
      : Promise.resolve(import.meta.env.VITE_API_URL || DEFAULT_API_URL)
  }
  return baseUrlPromise
}

export function resetApiBaseUrl(): void {
  baseUrlPromise = null
}

/** The desktop shell is launching the backend again (it exited and is being restarted). */
export class BackendRestarting extends Error {
  constructor() {
    super('the backend is restarting')
    this.name = 'BackendRestarting'
  }
}

/** The desktop shell gave up on the backend: only «Reintentar» starts it again. */
export class BackendFailed extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'BackendFailed'
  }
}

/**
 * The URL to probe the backend at, without waiting: in the desktop app the shell is asked
 * every time, because a restarted backend listens on another port (phase 08).
 */
export async function currentBackendUrl(): Promise<string> {
  if (!isTauri()) return getApiBaseUrl()
  let url: string
  try {
    url = await invoke<string>('backend_url')
  } catch (error) {
    resetApiBaseUrl()
    if (error === BACKEND_STARTING) throw new BackendRestarting()
    throw new BackendFailed(String(error))
  }
  const cached = baseUrlPromise ? await baseUrlPromise.catch(() => null) : null
  if (cached !== url) baseUrlPromise = Promise.resolve(url)
  return url
}

/** «Reintentar» after the shell gave up on the backend. */
export async function restartBackend(): Promise<void> {
  resetApiBaseUrl()
  await invoke('restart_backend')
}

/** «Abrir logs»: the backend's logs folder (works with the backend down). */
export async function openBackendLogs(): Promise<void> {
  await invoke('open_logs')
}

/** Error returned by the backend: `{"detail": {"code", "message", "field?"}}`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly field?: string

  constructor(status: number, code: string, message: string, field?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.field = field
  }
}

async function toApiError(response: Response, path: string): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      detail?: { code?: string; message?: string; field?: string }
    }
    const detail = body.detail ?? {}
    return new ApiError(
      response.status,
      detail.code ?? `http_${response.status}`,
      detail.message ?? `HTTP ${response.status} on ${path}`,
      detail.field,
    )
  } catch {
    return new ApiError(response.status, `http_${response.status}`, `HTTP ${response.status}`)
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getApiBaseUrl()
  const response = await fetch(`${base}${path}`, init)
  if (!response.ok) throw await toApiError(response, path)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) => apiFetch<T>(path, jsonInit('POST', body)),
  patch: <T>(path: string, body: unknown) => apiFetch<T>(path, jsonInit('PATCH', body)),
  put: <T>(path: string, body: unknown) => apiFetch<T>(path, jsonInit('PUT', body)),
  delete: (path: string) => apiFetch<void>(path, jsonInit('DELETE')),
}
