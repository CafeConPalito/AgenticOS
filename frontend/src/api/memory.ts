import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ProjectMemory, MemoryNote } from './types'

export const memoryKeys = {
  all: ['memory'] as const,
  project: (projectId: string) => ['memory', projectId] as const,
}

export function useProjectMemory(projectId: string) {
  return useQuery({
    queryKey: memoryKeys.project(projectId),
    queryFn: () => api.get<ProjectMemory>(`/api/projects/${projectId}/memory`),
  })
}

function useInvalidateMemory(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: memoryKeys.project(projectId) })
}

export function useAddNote(projectId: string) {
  const invalidate = useInvalidateMemory(projectId)
  return useMutation({
    mutationFn: (text: string) =>
      api.post<MemoryNote>(`/api/projects/${projectId}/memory`, { text }),
    onSuccess: invalidate,
  })
}

export function useEditNote(projectId: string) {
  const invalidate = useInvalidateMemory(projectId)
  return useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      api.patch<MemoryNote>(`/api/projects/${projectId}/memory/${id}`, { text }),
    onSuccess: invalidate,
  })
}

export function useDeleteNote(projectId: string) {
  const invalidate = useInvalidateMemory(projectId)
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/projects/${projectId}/memory/${id}`),
    onSuccess: invalidate,
  })
}
