import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { invalidateRepo } from './git'
import type { Task } from './types'

/** Integrating the branches of a task into their bases (phase 12, block 5). */

export type IntegrationMode = 'merge' | 'squash' | 'rebase'
export type RepoState = 'nothing' | 'integrated' | 'clean' | 'conflicts' | 'blocked' | 'missing'
export type Outcome = 'integrated' | 'nothing' | 'conflicts' | 'blocked' | 'failed' | 'missing'

export interface RepoCheck {
  repo_id: string
  name: string
  branch: string
  base: string | null
  ahead: number
  behind: number
  state: RepoState
  conflicts: string[]
  /** The folder where the base is checked out (null: nothing on disk moves). */
  active_in: string | null
  /** Uncommitted files in that folder, when that is what blocks it. */
  dirty: string[]
  integrated_at: string | null
  integrated_sha: string | null
}

export interface IntegrationCheck {
  task_id: string
  repos: RepoCheck[]
  can_integrate: boolean
  pending: number
}

export interface RepoOutcome {
  repo_id: string
  name: string
  status: Outcome
  sha: string | null
  conflicts: string[]
  dirty: string[]
  error_code: string | null
  message: string
  pushed: boolean
}

export interface IntegrationResult {
  group_id: string
  repos: RepoOutcome[]
  stopped: boolean
  integrated: number
}

export interface Resolution {
  repo_id: string
  name: string
  /** Empty: the base merged cleanly, nothing to resolve. */
  path: string
  conflicts: string[]
}

export const integrationKey = (taskId: string) => ['tasks', taskId, 'integration'] as const

export function useIntegration(taskId: string, enabled = true) {
  return useQuery({
    queryKey: integrationKey(taskId),
    queryFn: () => api.get<IntegrationCheck>(`/api/tasks/${taskId}/integration`),
    enabled,
    staleTime: 0,
  })
}

/** After anything that moves a base or a task branch: the check and the repositories change. */
function useRefresh(taskId: string) {
  const queryClient = useQueryClient()
  return (repoIds: string[] = []) => {
    void queryClient.invalidateQueries({ queryKey: integrationKey(taskId) })
    repoIds.forEach((id) => invalidateRepo(queryClient, id))
  }
}

export function useIntegrate(taskId: string) {
  const refresh = useRefresh(taskId)
  return useMutation({
    mutationFn: (body: { mode?: IntegrationMode; push: boolean; delete_branches: boolean }) =>
      api.post<IntegrationResult>(`/api/tasks/${taskId}/integrate`, body),
    onSettled: (result) => refresh(result?.repos.map((r) => r.repo_id)),
  })
}

export function useUndoIntegration(taskId: string) {
  const refresh = useRefresh(taskId)
  return useMutation({
    mutationFn: () => api.post<{ undone: number }>(`/api/tasks/${taskId}/integration/undo`, {}),
    onSettled: () => refresh(),
  })
}

export function useStartResolution(taskId: string) {
  const refresh = useRefresh(taskId)
  return useMutation({
    mutationFn: (repoId: string) =>
      api.post<Resolution>(`/api/tasks/${taskId}/integration/resolution`, { repo_id: repoId }),
    onSettled: () => refresh(),
  })
}

export function useFinishResolution(taskId: string) {
  const refresh = useRefresh(taskId)
  return useMutation({
    mutationFn: (repoId: string) =>
      api.post<void>(`/api/tasks/${taskId}/integration/resolution/finish`, { repo_id: repoId }),
    onSettled: () => refresh(),
  })
}

export function useResolveConflicts(taskId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (agentId: string) =>
      api.post<Task>(`/api/tasks/${taskId}/resolve-conflicts`, { agent_id: agentId }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })
}
