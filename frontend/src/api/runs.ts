import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { ACTIVE_RUN_STATUSES, type Run } from './types'

export interface RunFilters {
  agentId?: string
  projectId?: string
  active?: boolean
}

export const runKeys = {
  all: ['runs'] as const,
  list: (filters: RunFilters) => ['runs', 'list', filters] as const,
  detail: (id: string) => ['runs', id] as const,
}

export const isActive = (run: Pick<Run, 'status'>) => ACTIVE_RUN_STATUSES.includes(run.status)

function query(filters: RunFilters): string {
  const params = new URLSearchParams()
  if (filters.agentId) params.set('agent_id', filters.agentId)
  if (filters.projectId) params.set('project_id', filters.projectId)
  if (filters.active !== undefined) params.set('active', String(filters.active))
  const text = params.toString()
  return text ? `?${text}` : ''
}

export function useRuns(filters: RunFilters = {}) {
  return useQuery({
    queryKey: runKeys.list(filters),
    queryFn: () => api.get<Run[]>(`/api/runs${query(filters)}`),
    // Live status comes through each run's WebSocket; lists refresh while something runs.
    refetchInterval: (q) => (q.state.data?.some(isActive) || filters.active ? 3000 : false),
  })
}

export function useRun(id: string | undefined) {
  return useQuery({
    queryKey: runKeys.detail(id ?? ''),
    queryFn: () => api.get<Run>(`/api/runs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && isActive(q.state.data) ? 3000 : false),
  })
}

function useInvalidateRuns() {
  const queryClient = useQueryClient()
  return (run?: Run) => {
    if (run) queryClient.setQueryData(runKeys.detail(run.id), run)
    return queryClient.invalidateQueries({ queryKey: runKeys.all })
  }
}

export function useLaunchRun() {
  const invalidate = useInvalidateRuns()
  return useMutation({
    mutationFn: (body: { agent_id: string; project_id: string; prompt: string }) =>
      api.post<Run>('/api/runs', body),
    onSuccess: (run) => invalidate(run),
  })
}

export function useStopRun() {
  const invalidate = useInvalidateRuns()
  return useMutation({
    mutationFn: (id: string) => api.post<Run>(`/api/runs/${id}/stop`),
    onSuccess: (run) => invalidate(run),
  })
}

export function useRunControl(id: string) {
  const invalidate = useInvalidateRuns()
  return useMutation({
    mutationFn: (body: { action: 'take' | 'release'; client_id: string }) =>
      api.post<Run>(`/api/runs/${id}/control`, body),
    onSuccess: (run) => invalidate(run),
  })
}
