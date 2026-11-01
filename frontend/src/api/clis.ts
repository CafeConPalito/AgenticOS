import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { AgyQuotaState, CliId, CliInfo } from './types'

const KEY = ['clis'] as const

export function useClis() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api.get<CliInfo[]>('/api/clis'),
    staleTime: 5 * 60 * 1000,
  })
}

/** Reads the CLIs as the backend has them now, without probing them again (an installation
 * that just ended was already probed there). */
export function useReloadClis() {
  const queryClient = useQueryClient()
  return async () => {
    const fresh = await api.get<CliInfo[]>('/api/clis')
    queryClient.setQueryData(KEY, fresh)
    return fresh
  }
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

/** «Añadir CLI» (phase 23): runs the CLI's official installer, in a terminal. */
export function useInstallCli() {
  return useMutation({
    mutationFn: (cli: CliId) => api.post<void>(`/api/clis/${cli}/install`),
  })
}

const AGY_QUOTA = ['clis', 'agy', 'quota'] as const

export function useAgyQuota() {
  return useQuery({
    queryKey: AGY_QUOTA,
    queryFn: () => api.get<AgyQuotaState>('/api/clis/agy/quota'),
  })
}

/** Turns on or off the reading of agy's quota (it edits agy's settings, see the backend). */
export function useSetAgyQuota() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => api.put<AgyQuotaState>('/api/clis/agy/quota', { enabled }),
    onSuccess: (state) => queryClient.setQueryData(AGY_QUOTA, state),
    onSettled: () => queryClient.invalidateQueries({ queryKey: AGY_QUOTA }),
  })
}
