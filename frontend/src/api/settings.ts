import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

/** The data folder (phase 08): where it is, what it takes, and moving it. */
export interface DataDir {
  path: string
  is_default: boolean
  database_bytes: number
  sessions_bytes: number
  /** The library: Markdown and pictures extracted (the originals stay where they are). */
  knowledge_bytes: number
  /** Downloaded models and engines. */
  models_bytes: number
  skills_bytes: number
  logs_bytes: number
  total_bytes: number
  /** The last move that failed: the data stayed where it was. */
  last_error: string | null
}

export const settingsKeys = {
  dataDir: ['settings', 'data-dir'] as const,
}

export function useDataDir() {
  return useQuery({
    queryKey: settingsKeys.dataDir,
    queryFn: () => api.get<DataDir>('/api/settings/data-dir'),
  })
}

export function useOpenDataDir() {
  return useMutation({ mutationFn: () => api.post<null>('/api/settings/data-dir/open') })
}

export function useMoveDataDir() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (to: string) =>
      api.post<{ to: string; restarting: boolean }>('/api/settings/data-dir/move', { to }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: settingsKeys.dataDir }),
  })
}
