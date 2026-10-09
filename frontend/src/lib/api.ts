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
  delete: (path: string) => apiFetch<void>(path, jsonInit('DELETE')),
}
