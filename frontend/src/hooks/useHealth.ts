import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface Health {
  status: string
  name: string
  version: string
}

export type BackendState = 'connecting' | 'connected' | 'disconnected'

export const HEALTH_INTERVAL_MS = 5000
/** A backend that accepts the connection but never answers must count as disconnected. */
export const HEALTH_TIMEOUT_MS = 4000

export function useHealth() {
  const query = useQuery({
    queryKey: ['health'],
    queryFn: () =>
      apiFetch<Health>('/api/health', { signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS) }),
    refetchInterval: HEALTH_INTERVAL_MS,
    retry: false,
  })
  const state: BackendState = query.isPending
    ? 'connecting'
    : query.isError
      ? 'disconnected'
      : 'connected'
  return { ...query, state }
}
