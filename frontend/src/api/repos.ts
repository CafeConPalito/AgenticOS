import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { GitInfo } from './types'

/** The git repositories of a project (phase 12): found in its folder or linked from outside. */

export type PullMode = 'ff_only' | 'merge' | 'rebase'

export interface ProjectRepo {
  id: string
  project_id: string
  name: string
  path: string
  /** Relative to the project folder ("" is the folder itself); null for a linked repository. */
  rel_path: string | null
  base_branch: string | null
  /** Tasks work in it (it gets a worktree). */
  participates: boolean
  /** Outside the project folder. */
  linked: boolean
  /** The folder is gone or no longer a repository. */
  missing: boolean
  position: number
  pull_mode: PullMode
  forge: 'github' | 'gitlab' | null
  git: GitInfo | null
}

export interface RepoUpdate {
  name?: string
  base_branch?: string
  participates?: boolean
  pull_mode?: PullMode
  forge?: 'github' | 'gitlab' | null
}

export const repoKeys = {
  project: (projectId: string) => ['repos', projectId] as const,
}

export function useRepos(projectId: string) {
  return useQuery({
    queryKey: repoKeys.project(projectId),
    queryFn: () => api.get<ProjectRepo[]>(`/api/projects/${projectId}/repos`),
  })
}

function useRefresh(projectId: string) {
  const queryClient = useQueryClient()
  return (repos?: ProjectRepo[]) => {
    if (repos) queryClient.setQueryData(repoKeys.project(projectId), repos)
    return queryClient.invalidateQueries({ queryKey: repoKeys.project(projectId) })
  }
}

/** «Volver a buscar»: looks for repositories again. */
export function useScanRepos(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: () => api.post<ProjectRepo[]>(`/api/projects/${projectId}/repos/scan`, {}),
    onSuccess: (repos) => refresh(repos),
  })
}

export function useLinkRepo(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: { path: string; name?: string }) =>
      api.post<ProjectRepo>(`/api/projects/${projectId}/repos`, body),
    onSuccess: () => refresh(),
  })
}

/** «Inicializar repositorio»: makes the project's folder (or a subfolder) a git repository. */
export function useInitRepo(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: { branch: string; path?: string }) =>
      api.post<{ path: string }>(`/api/projects/${projectId}/repos/init`, body),
    onSuccess: () => refresh(),
  })
}

export function useUpdateRepo(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, ...body }: RepoUpdate & { id: string }) =>
      api.patch<ProjectRepo>(`/api/repos/${id}`, body),
    onSuccess: () => refresh(),
  })
}

export function useRemoveRepo(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/repos/${id}`),
    onSuccess: () => refresh(),
  })
}
