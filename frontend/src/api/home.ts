import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Home } from './types'

export const homeKeys = { all: ['home'] as const }

const POLL_MS = 3000

/** Everything Inicio and the navigation counters need, polled like the Inbox. */
export function useHome() {
  return useQuery({
    queryKey: homeKeys.all,
    queryFn: () => api.get<Home>('/api/home'),
    refetchInterval: POLL_MS,
  })
}
