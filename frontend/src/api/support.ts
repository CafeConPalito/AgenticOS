import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

/** What «Preparar registros para enviar» would put in the zip (phase 20). */
export interface LogsPreview {
  files: { name: string; size: number }[]
  total: number
  default_path: string
}

export interface LogsBundle {
  path: string
  size: number
  files: string[]
  redactions: Record<string, number>
}

export function useLogsPreview(enabled: boolean) {
  return useQuery({
    queryKey: ['support', 'logs'],
    queryFn: () => api.get<LogsPreview>('/api/support/logs'),
    enabled,
    staleTime: 0,
  })
}

export function useBundleLogs() {
  return useMutation({
    mutationFn: (path: string | null) =>
      api.post<LogsBundle>('/api/support/logs/bundle', path ? { path } : {}),
  })
}

export function revealBundle(path: string) {
  return api.post<void>('/api/support/logs/reveal', { path })
}
