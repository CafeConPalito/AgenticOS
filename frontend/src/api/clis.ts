import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CliInfo } from './types'

const KEY = ['clis'] as const

export function useClis() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api.get<CliInfo[]>('/api/clis'),
    staleTime: 5 * 60 * 1000,
  })
}

/** Forces the backend to re-probe the CLIs (version, login, models). */
export function useRefreshClis() {
  const queryClient = useQueryClient()
  return async () => {
    const fresh = await api.get<CliInfo[]>('/api/clis?refresh=true')
    queryClient.setQueryData(KEY, fresh)
    return fresh
  }
}
