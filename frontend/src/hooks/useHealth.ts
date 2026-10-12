import { useQuery } from '@tanstack/react-query'
import { BackendFailed, BackendRestarting, currentBackendUrl } from '@/lib/api'

export interface Health {
  status: string
  name: string
  version: string
  /** Where the backend answered (the port changes when the desktop app restarts it). */
  url: string
}

/**
 * `reconnecting`: the desktop app is restarting the backend; `failed`: it gave up (the UI
 * offers «Reintentar» and «Abrir logs»); `disconnected`: no answer (browser, or a hang).
 */
export type BackendState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed'

export const HEALTH_INTERVAL_MS = 5000
/** A backend that accepts the connection but never answers must count as disconnected. */
export const HEALTH_TIMEOUT_MS = 4000
/** Faster while the backend restarts, so the app is back as soon as it is. */
export const RECONNECT_INTERVAL_MS = 1000

async function probe(): Promise<Health> {
  const url = await currentBackendUrl()
  const response = await fetch(`${url}/api/health`, {
    signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return { ...((await response.json()) as Omit<Health, 'url'>), url }
}

export function useHealth() {
  const query = useQuery({
    queryKey: ['health'],
    queryFn: probe,
    refetchInterval: (q) =>
      q.state.error instanceof BackendRestarting ? RECONNECT_INTERVAL_MS : HEALTH_INTERVAL_MS,
    retry: false,
  })
  const restarting = query.error instanceof BackendRestarting
  // Never connected yet: the sidecar is still booting (not a restart).
  const state: BackendState =
    query.isPending || (restarting && !query.data)
      ? 'connecting'
      : restarting
        ? 'reconnecting'
        : query.error instanceof BackendFailed
          ? 'failed'
          : query.isError
            ? 'disconnected'
            : 'connected'
  return { ...query, state }
}
