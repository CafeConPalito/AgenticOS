import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { agentKeys } from './agents'
import { homeKeys } from './home'
import type { Team } from './types'

export const teamKeys = { all: ['teams'] as const }

export function useTeams() {
  return useQuery({ queryKey: teamKeys.all, queryFn: () => api.get<Team[]>('/api/teams') })
}

/** Teams hold agents: a change to one is a change to the others. */
function useRefreshTeams() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: teamKeys.all }),
      queryClient.invalidateQueries({ queryKey: agentKeys.all }),
      queryClient.invalidateQueries({ queryKey: homeKeys.all }),
    ])
}

export interface TeamWrite {
  name: string
  description: string
  agent_ids: string[]
}

export function useCreateTeam() {
  const refresh = useRefreshTeams()
  return useMutation({
    mutationFn: (body: TeamWrite) => api.post<Team>('/api/teams', body),
    onSuccess: refresh,
  })
}

export function useUpdateTeam(id: string) {
  const refresh = useRefreshTeams()
  return useMutation({
    mutationFn: (body: Partial<TeamWrite>) => api.patch<Team>(`/api/teams/${id}`, body),
    onSuccess: refresh,
  })
}

export function useDeleteTeam() {
  const refresh = useRefreshTeams()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/teams/${id}`),
    onSuccess: refresh,
  })
}
