import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { taskKeys } from './tasks'
import type {
  CopiedPipeline,
  GraphIssue,
  Pipeline,
  PipelineTemplateId,
  PipelineWrite,
  PreviewRequest,
  PreviewResult,
  TemplateApply,
  TemplatePlanStage,
} from './types'

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

/** Phase 24: applies a template; with `create`, the missing agents are made in one step. */
export function usePipelineFromTemplate(projectId: string) {
  const queryClient = useQueryClient()
  const set = useSetPipeline(projectId)
  return useMutation({
    mutationFn: (body: TemplateApply) =>
      api.post<Pipeline>(`/api/projects/${projectId}/pipeline/template`, body),
    onSuccess: async (pipeline) => {
      await set(pipeline)
      // New agents and maybe a new team.
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
      return queryClient.invalidateQueries({ queryKey: ['teams'] })
    },
  })
}

/** Phase 24: the agent each stage of a template would get here. */
export function useTemplatePlan(template: PipelineTemplateId, enabled = true) {
  return useQuery({
    queryKey: ['pipeline-template-plan', template],
    queryFn: () => api.get<TemplatePlanStage[]>(`/api/pipeline-templates/${template}/plan`),
    enabled,
  })
}

/** Phase 24: copies the pipeline of another project. */
export function useCopyPipeline(projectId: string) {
  const set = useSetPipeline(projectId)
  return useMutation({
    mutationFn: (fromProjectId: string) =>
      api.post<CopiedPipeline>(`/api/projects/${projectId}/pipeline/copy`, {
        from_project_id: fromProjectId,
      }),
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

/** The problems the server finds in a pipeline as edited, without saving it. */
export function useValidatePipeline(projectId: string) {
  return useMutation({
    mutationFn: (body: PipelineWrite) =>
      api.post<GraphIssue[]>(`/api/projects/${projectId}/pipeline/validate`, body),
  })
}

/** «Probar»: what the decider would choose for an example task (it costs a real call). */
export function usePreviewDecision(projectId: string) {
  return useMutation({
    mutationFn: (body: PreviewRequest) =>
      api.post<PreviewResult>(`/api/projects/${projectId}/pipeline/decide-preview`, body),
  })
}
