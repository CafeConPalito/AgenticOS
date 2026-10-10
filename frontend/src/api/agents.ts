import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Agent, AgentFields, AgentTemplate } from './types'

export const agentKeys = {
  all: ['agents'] as const,
  detail: (id: string) => ['agents', id] as const,
  templates: ['agent-templates'] as const,
}

export function useAgents() {
  return useQuery({ queryKey: agentKeys.all, queryFn: () => api.get<Agent[]>('/api/agents') })
}

export function useAgent(id: string | undefined) {
  return useQuery({
    queryKey: agentKeys.detail(id ?? ''),
    queryFn: () => api.get<Agent>(`/api/agents/${id}`),
    enabled: Boolean(id),
  })
}

export function useAgentTemplates() {
  return useQuery({
    queryKey: agentKeys.templates,
    queryFn: () => api.get<AgentTemplate[]>('/api/agent-templates'),
    staleTime: Infinity,
  })
}

function useInvalidateAgents() {
  const queryClient = useQueryClient()
  return (agent?: Agent) => {
    if (agent) queryClient.setQueryData(agentKeys.detail(agent.id), agent)
    return queryClient.invalidateQueries({ queryKey: agentKeys.all, exact: true })
  }
}

export function useCreateAgent() {
  const invalidate = useInvalidateAgents()
  return useMutation({
    mutationFn: (body: Partial<AgentFields> & { template?: string }) =>
      api.post<Agent>('/api/agents', body),
    onSuccess: (agent) => invalidate(agent),
  })
}

export function useUpdateAgent(id: string) {
  const invalidate = useInvalidateAgents()
  return useMutation({
    mutationFn: (body: Partial<AgentFields>) => api.patch<Agent>(`/api/agents/${id}`, body),
    onSuccess: (agent) => invalidate(agent),
  })
}

export function useDuplicateAgent() {
  const invalidate = useInvalidateAgents()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.post<Agent>(`/api/agents/${id}/duplicate`, { name }),
    onSuccess: (agent) => invalidate(agent),
  })
}

export function useDeleteAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/agents/${id}`),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: agentKeys.detail(id) })
      return queryClient.invalidateQueries({ queryKey: agentKeys.all, exact: true })
    },
  })
}
