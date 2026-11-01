import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CliId, Run } from './types'

/** Terminals of the person's own (phase 23, ADR 0029): runs of kind «terminal». */
export const terminalKeys = { all: ['terminals'] as const }

export function useTerminals() {
  return useQuery({
    queryKey: terminalKeys.all,
    queryFn: () => api.get<Run[]>('/api/terminals'),
    // A CLI closed from inside (`/exit`) leaves the list without anyone asking.
    refetchInterval: 5000,
  })
}

export interface TerminalRequest {
  cli: CliId
  /** Null: the CLI's default account. */
  account_id: string | null
  /** A folder; `~` is the personal one. */
  cwd: string
}

export function useOpenTerminal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TerminalRequest) => api.post<Run>('/api/terminals', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: terminalKeys.all }),
  })
}

export function useCloseTerminal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/terminals/${id}`),
    onSuccess: (_, id) =>
      queryClient.setQueryData<Run[]>(terminalKeys.all, (runs) =>
        runs?.filter((run) => run.id !== id),
      ),
  })
}
