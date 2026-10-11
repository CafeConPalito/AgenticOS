import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { taskKeys } from './tasks'
import type { Pipeline, PipelineWrite } from './types'

export const pipelineKeys = {
  project: (projectId: string) => ['pipeline', projectId] as const,
}

export function usePipeline(projectId: string, enabled = true) {
  return useQuery({
    queryKey: pipelineKeys.project(projectId),
    queryFn: () => api.get<Pipeline | null>(`/api/projects/${projectId}/pipeline`),
    enabled: enabled && Boolean(projectId),
  })
}

function useSetPipeline(projectId: string) {
  const queryClient = useQueryClient()
  return (pipeline: Pipeline | null) => {
    queryClient.setQueryData(pipelineKeys.project(projectId), pipeline)
    // Stage names and agents show on the tasks.
    return queryClient.invalidateQueries({ queryKey: taskKeys.all })
  }
}

export function useSavePipeline(projectId: string) {
  const set = useSetPipeline(projectId)
  return useMutation({
    mutationFn: (body: PipelineWrite) =>
      api.put<Pipeline>(`/api/projects/${projectId}/pipeline`, body),
    onSuccess: (pipeline) => set(pipeline),
  })
}

export function usePipelineFromTemplate(projectId: string) {
  const set = useSetPipeline(projectId)
  return useMutation({
    mutationFn: (template: 'web') =>
      api.post<Pipeline>(`/api/projects/${projectId}/pipeline/template`, { template }),
    onSuccess: (pipeline) => set(pipeline),
  })
}

export function useDeletePipeline(projectId: string) {
  const set = useSetPipeline(projectId)
  return useMutation({
    mutationFn: () => api.delete(`/api/projects/${projectId}/pipeline`),
    onSuccess: () => set(null),
  })
}
