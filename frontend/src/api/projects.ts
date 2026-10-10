import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Project, ProjectFields } from './types'

export const projectKeys = {
  all: ['projects'] as const,
  detail: (id: string) => ['projects', id] as const,
}

export function useProjects() {
  return useQuery({
    queryKey: projectKeys.all,
    queryFn: () => api.get<Project[]>('/api/projects'),
  })
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.detail(id ?? ''),
    queryFn: () => api.get<Project>(`/api/projects/${id}`),
    enabled: Boolean(id),
  })
}

function useInvalidateProjects() {
  const queryClient = useQueryClient()
  return (project?: Project) => {
    if (project) queryClient.setQueryData(projectKeys.detail(project.id), project)
    return queryClient.invalidateQueries({ queryKey: projectKeys.all, exact: true })
  }
}

export type ProjectCreate = Pick<ProjectFields, 'name' | 'path'> &
  Partial<ProjectFields> & { create_folder?: boolean }

export function useCreateProject() {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.post<Project>('/api/projects', body),
    onSuccess: (project) => invalidate(project),
  })
}

export function useUpdateProject(id: string) {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: (body: Partial<ProjectFields>) => api.patch<Project>(`/api/projects/${id}`, body),
    onSuccess: (project) => invalidate(project),
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/projects/${id}`),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: projectKeys.detail(id) })
      return queryClient.invalidateQueries({ queryKey: projectKeys.all, exact: true })
    },
  })
}

export function useOpenProjectFolder() {
  return useMutation({
    mutationFn: (id: string) => api.post<void>(`/api/projects/${id}/open`),
  })
}
