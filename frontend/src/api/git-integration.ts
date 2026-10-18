import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { type CommitInfo, useRepoMutation } from './git'

/** Merge, rebase, conflicts and «Deshacer» of the Git tab (phase 12). */

export type OpStatus = 'done' | 'conflicts' | 'up_to_date' | 'squashed' | 'stopped'

/** How a merge, rebase, cherry-pick or revert ended: a conflict is a result, not an error. */
export interface OpResult {
  status: OpStatus
  conflicts: string[]
  message: string
}

export type MergeMode = 'no_ff' | 'ff' | 'squash'
export type ResetMode = 'soft' | 'mixed' | 'hard'
export type TodoAction = 'pick' | 'reword' | 'squash' | 'fixup' | 'edit' | 'drop'

export interface TodoLine {
  action: TodoAction
  sha: string
  message?: string
}

export interface ConflictFile {
  path: string
  base: string | null
  /** Null: that side deleted the file. */
  ours: string | null
  theirs: string | null
  /** The file as git left it, with its conflict markers. */
  merged: string | null
  binary: boolean
  ours_label: string
  theirs_label: string
}

export interface OperationRead {
  id: string
  kind: string
  label: string
  at: string
  group_id: string | null
  undone: boolean
  in_progress: boolean
  /** Why it cannot be undone now; null when it can. */
  blocked_by: string | null
  /** It threw away uncommitted files, which undoing brings back. */
  lost_files: boolean
}

export const integrationKeys = {
  operations: (repoId: string) => ['git', 'repo', repoId, 'operations'] as const,
  conflict: (repoId: string, path: string) => ['git', 'repo', repoId, 'conflict', path] as const,
  plan: (repoId: string, base: string) => ['git', 'repo', repoId, 'plan', base] as const,
}

export function useMerge(repoId: string) {
  return useRepoMutation(repoId, (body: { ref: string; mode?: MergeMode; message?: string }) =>
    api.post<OpResult>(`/api/repos/${repoId}/merge`, body),
  )
}

export function useRebase(repoId: string) {
  return useRepoMutation(repoId, (onto: string) =>
    api.post<OpResult>(`/api/repos/${repoId}/rebase`, { onto }),
  )
}

export function useCherryPick(repoId: string) {
  return useRepoMutation(repoId, (shas: string[]) =>
    api.post<OpResult>(`/api/repos/${repoId}/cherry-pick`, { shas }),
  )
}

export function useRevert(repoId: string) {
  return useRepoMutation(repoId, (shas: string[]) =>
    api.post<OpResult>(`/api/repos/${repoId}/revert`, { shas }),
  )
}

export function useReset(repoId: string) {
  return useRepoMutation(repoId, (body: { ref: string; mode: ResetMode }) =>
    api.post<OpResult>(`/api/repos/${repoId}/reset`, { ...body, confirm: body.mode === 'hard' }),
  )
}

export function useRebasePlan(repoId: string, base: string | null) {
  return useQuery({
    queryKey: integrationKeys.plan(repoId, base ?? ''),
    queryFn: () =>
      api.get<CommitInfo[]>(
        `/api/repos/${repoId}/rebase/plan?base=${encodeURIComponent(base ?? '')}`,
      ),
    enabled: Boolean(base),
    staleTime: 0,
  })
}

export function useInteractiveRebase(repoId: string) {
  return useRepoMutation(repoId, (body: { base: string; items: TodoLine[] }) =>
    api.post<OpResult>(`/api/repos/${repoId}/rebase/interactive`, body),
  )
}

/** Carries on, skips or abandons the operation that stopped. */
export function useProceed(repoId: string) {
  return useRepoMutation(repoId, (action: 'continue' | 'skip' | 'abort') =>
    api.post<OpResult>(`/api/repos/${repoId}/operation/${action}`, {}),
  )
}

export function useConflictFile(repoId: string, path: string | null) {
  return useQuery({
    queryKey: integrationKeys.conflict(repoId, path ?? ''),
    queryFn: () =>
      api.get<ConflictFile>(
        `/api/repos/${repoId}/conflicts/file?path=${encodeURIComponent(path ?? '')}`,
      ),
    enabled: Boolean(path),
    staleTime: 0,
  })
}

export function useResolveConflict(repoId: string) {
  return useRepoMutation(repoId, (body: { path: string; content: string }) =>
    api.post<void>(`/api/repos/${repoId}/conflicts/resolve`, body),
  )
}

export function useTakeSide(repoId: string) {
  return useRepoMutation(repoId, (body: { path: string; side: 'ours' | 'theirs' }) =>
    api.post<void>(`/api/repos/${repoId}/conflicts/take`, body),
  )
}

export function useOperations(repoId: string) {
  return useQuery({
    queryKey: integrationKeys.operations(repoId),
    queryFn: () => api.get<OperationRead[]>(`/api/repos/${repoId}/operations`),
  })
}

export function useUndo(repoId: string) {
  return useRepoMutation(repoId, (operationId: string) =>
    api.post<void>(`/api/repos/${repoId}/operations/${operationId}/undo`, {}),
  )
}
