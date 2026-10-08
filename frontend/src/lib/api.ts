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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getApiBaseUrl()
  const response = await fetch(`${base}${path}`, init)
  if (!response.ok) throw new Error(`HTTP ${response.status} on ${path}`)
  return (await response.json()) as T
}
