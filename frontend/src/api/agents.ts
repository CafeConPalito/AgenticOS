import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiFetch, getApiBaseUrl } from '@/lib/api'
import type { Agent, AgentFields, AgentTemplate } from './types'

export const agentKeys = {
  all: ['agents'] as const,
  detail: (id: string) => ['agents', id] as const,
  templates: ['agent-templates'] as const,
}

export function useAgents({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: agentKeys.all,
    queryFn: () => api.get<Agent[]>('/api/agents'),
    enabled,
  })
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

/**
 * Phase 20: the cropped photo of an agent, sent as it is (the original never leaves the
 * browser); the backend stores it again and answers the agent with its new `avatar`.
 */
export function useUploadAvatar(id: string) {
  const invalidate = useInvalidateAgents()
  return useMutation({
    mutationFn: (crop: Blob) =>
      apiFetch<Agent>(`/api/agents/${id}/avatar`, {
        method: 'PUT',
        headers: { 'Content-Type': crop.type || 'image/webp' },
        body: crop,
      }),
    onSuccess: (agent) => invalidate(agent),
  })
}

/** Back to the main CLI before the window resets. */
export function useClearFallback() {
  const invalidate = useInvalidateAgents()
  return useMutation({
    mutationFn: (id: string) => api.post<Agent>(`/api/agents/${id}/fallback/clear`),
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

// ------------------------------------------------------------------ templates and files (phase 19)

function useRefreshTemplates() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: agentKeys.templates })
}

export function useSaveAsTemplate() {
  const refresh = useRefreshTemplates()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name?: string }) =>
      api.post<AgentTemplate>(`/api/agents/${id}/save-as-template`, name ? { name } : {}),
    onSuccess: refresh,
  })
}

export function useUpdateTemplate() {
  const refresh = useRefreshTemplates()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; description?: string }) =>
      api.patch<AgentTemplate>(`/api/agent-templates/${id}`, body),
    onSuccess: refresh,
  })
}

export function useDuplicateTemplate() {
  const refresh = useRefreshTemplates()
  return useMutation({
    mutationFn: (id: string) => api.post<AgentTemplate>(`/api/agent-templates/${id}/duplicate`),
    onSuccess: refresh,
  })
}

export function useDeleteTemplate() {
  const refresh = useRefreshTemplates()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/agent-templates/${id}`),
    onSuccess: refresh,
  })
}

/** Downloads the agent as `<name>.agent.json` (works in the browser and in Tauri's webview). */
export async function downloadAgent(agent: Agent): Promise<void> {
  const base = await getApiBaseUrl()
  const response = await fetch(`${base}/api/agents/${agent.id}/export`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const text = JSON.stringify(await response.json(), null, 2)
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${agent.name.replace(/[^\w.-]+/g, '-') || 'agente'}.agent.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export interface ImportPreview {
  agent: Partial<AgentFields>
  missing_skills: string[]
  missing_connections: string[]
  missing_knowledge: string[]
  own_skills: string[]
  cli_installed: boolean
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: (payload: unknown) =>
      api.post<ImportPreview>('/api/agents/import/preview', { payload }),
  })
}

export function useImportAgent() {
  const invalidate = useInvalidateAgents()
  return useMutation({
    mutationFn: (body: { payload: unknown; name?: string }) =>
      api.post<{ agent: Agent; notes: string[] }>('/api/agents/import', body),
    onSuccess: (result) => invalidate(result.agent),
  })
}
