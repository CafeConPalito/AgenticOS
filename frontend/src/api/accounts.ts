import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { homeKeys } from './home'
import { taskKeys } from './tasks'
import type { Account, CliId } from './types'

export const accountKeys = { all: ['accounts'] as const }

const POLL_MS = 5000

/** The CLI accounts with their session, limit and subscription windows (polled: a session
 * writes the windows while it works). */
export function useAccounts() {
  return useQuery({
    queryKey: accountKeys.all,
    queryFn: () => api.get<Account[]>('/api/accounts'),
    refetchInterval: POLL_MS,
  })
}

/** After anything that changes an account, what depends on it is read again. */
function useRefreshAccounts() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: accountKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['usage'] }),
      queryClient.invalidateQueries({ queryKey: ['inbox'] }),
      queryClient.invalidateQueries({ queryKey: homeKeys.all }),
      queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['settings', 'usage-limits'] }),
    ])
}

export function useCreateAccount() {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: (body: { cli: CliId; label?: string }) => api.post<Account>('/api/accounts', body),
    onSuccess: refresh,
  })
}

export function useUpdateAccount(id: string) {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: (body: { label?: string; daily_limit?: number | null }) =>
      api.patch<Account>(`/api/accounts/${id}`, body),
    onSuccess: refresh,
  })
}

export function useDeleteAccount() {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/accounts/${id}`),
    onSuccess: refresh,
  })
}

export function useMakeDefaultAccount() {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: (id: string) => api.post<Account>(`/api/accounts/${id}/default`),
    onSuccess: refresh,
  })
}

/** Asks the CLI again whether the account's session is alive (a few seconds). */
export function useProbeAccount() {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: (id: string) => api.post<Account>(`/api/accounts/${id}/probe`),
    onSuccess: refresh,
  })
}

/** Opens the CLI's login terminal for the account (the one already open, if any). */
export function useStartLogin() {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: ({ id, email }: { id: string; email?: string }) =>
      api.post<Account>(`/api/accounts/${id}/login`, { email: email ?? '' }),
    onSuccess: refresh,
  })
}

export function useCancelLogin() {
  const refresh = useRefreshAccounts()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/accounts/${id}/login`),
    onSuccess: refresh,
  })
}

/** The account an agent runs with: its own, or the default one of its CLI. */
export function accountOf(
  accounts: Account[] | undefined,
  agent: { cli: CliId; account_id: string | null },
): Account | undefined {
  if (!accounts) return undefined
  const own = agent.account_id ? accounts.find((a) => a.id === agent.account_id) : undefined
  return own && own.cli === agent.cli
    ? own
    : accounts.find((a) => a.cli === agent.cli && a.is_default)
}
