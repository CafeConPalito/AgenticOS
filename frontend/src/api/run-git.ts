import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { invalidateRepo } from './git'

/** What a run did with git, and undoing it (phase 12, block 7). */

export interface BranchMove {
  name: string
  /** Where it was when the run started (null: it did not exist). */
  start: string | null
  /** Where it ended (null: the run deleted it). */
  end: string | null
}

export interface RunPush {
  remote: string
  branch: string
  start: string | null
  end: string
  forced: boolean
}

export interface RunCommit {
  sha: string
  subject: string
  kind: 'commit' | 'amend' | 'merge' | 'rebase' | 'cherry-pick'
}

export interface RunActivity {
  commits: RunCommit[]
  branches: BranchMove[]
  tags: BranchMove[]
  pushes: RunPush[]
  head_start: string | null
  head_end: string | null
  undone: boolean
}

export interface RunRepoGit {
  repo_id: string | null
  name: string
  path: string
  /** Null: nothing was recorded for this run. */
  activity: RunActivity | null
  can_undo: boolean
  pushed: boolean
}

export interface UndoItem {
  branch: string
  result: 'reverted' | 'deleted' | 'skipped'
  reason: string | null
}

export interface UndoReport {
  repos: Record<string, { items: UndoItem[]; operation_id: string | null }>
}

export const runGitKey = (runId: string) => ['runs', runId, 'git'] as const

export function useRunGit(runId: string) {
  return useQuery({
    queryKey: runGitKey(runId),
    queryFn: () => api.get<RunRepoGit[]>(`/api/runs/${runId}/git`),
  })
}

export function useUndoRunGit(runId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<UndoReport>(`/api/runs/${runId}/git/undo`, { confirm: true }),
    onSettled: (report) => {
      void queryClient.invalidateQueries({ queryKey: runGitKey(runId) })
      Object.keys(report?.repos ?? {}).forEach((id) => invalidateRepo(queryClient, id))
    },
  })
}

/** Whether the run left anything worth a section. */
export function hasGitActivity(repos: RunRepoGit[] | undefined): boolean {
  return (repos ?? []).some(
    (r) =>
      r.activity &&
      (r.activity.commits.length ||
        r.activity.branches.length ||
        r.activity.tags.length ||
        r.activity.pushes.length),
  )
}
