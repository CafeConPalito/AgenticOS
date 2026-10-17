import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ChangesTotals } from './types'

/** What the runs, the tasks and the agents changed in their folders (phase 11). */

/** Why there is no diff: no git in the folder, no snapshots (old run) or they were deleted. */
export type ChangesState = 'ok' | 'no_git' | 'no_snapshots' | 'snapshot_missing'
export type FileStatus = 'added' | 'modified' | 'deleted' | 'renamed'
export type RefKind = 'base' | 'branch' | 'run_start' | 'run_end' | 'task_start' | 'now'

export interface RefLabel {
  kind: RefKind
  /** The branch of `base` and `branch`. */
  name: string
}

export interface FileChange {
  path: string
  /** Renames only. */
  old_path: string | null
  status: FileStatus
  additions: number
  deletions: number
  binary: boolean
  /** Binary files only, in bytes. */
  old_size: number | null
  new_size: number | null
  /** Lockfiles, build output and minified files: shown folded. */
  generated: boolean
}

export interface ChangesRunRef {
  id: string
  stage_name: string | null
  /** 1 = the first run of that stage. */
  attempt: number
  status: string
  started_at: string | null
  created_at: string
  totals: ChangesTotals | null
}

/** What changed in one repository of the project. */
export interface RepoChanges {
  /** The repository's id: which one a file request is about. */
  key: string
  name: string
  state: ChangesState
  live: boolean
  partial: boolean
  direct_folder: boolean
  from_ref: RefLabel | null
  to_ref: RefLabel | null
  totals: ChangesTotals
  files: FileChange[]
  /** Files over the list limit that are not in `files`. */
  truncated_files: number
  /** New files too big to be in the snapshots. */
  skipped_large: number
}

export interface Changes {
  /** "ok" when any repository has a diff; otherwise why there is none. */
  state: ChangesState
  /** The run is going: the end of the diff is the folder right now. */
  live: boolean
  /** Taken when the app reopened: may include later changes. */
  partial: boolean
  /** The folder is the user's too: everything that changed shows. */
  direct_folder: boolean
  /** All the repositories added up. */
  totals: ChangesTotals
  repos: RepoChanges[]
  /** Tasks only. */
  runs: ChangesRunRef[]
}

export interface DiffLine {
  kind: 'context' | 'add' | 'del'
  old_no: number | null
  new_no: number | null
  text: string
}

export interface Hunk {
  old_start: number
  old_lines: number
  new_start: number
  new_lines: number
  /** What git prints after the @@ (the enclosing function). */
  header: string
  lines: DiffLine[]
}

export interface FileDiff {
  path: string
  hunks: Hunk[]
  binary: boolean
  /** More lines than the limit: no content. */
  too_large: boolean
}

export interface AgentChangeRun {
  run_id: string
  project_id: string | null
  project_name: string
  task_id: string | null
  task_code: string | null
  task_title: string | null
  started_at: string | null
  created_at: string
  totals: ChangesTotals
}

/** What a diff is about: a run, or a whole task. */
export interface ChangesTarget {
  kind: 'run' | 'task'
  id: string
  /** Which repository, for the file requests (a project can have several). */
  repo?: string
}

export const changesKeys = {
  all: ['changes'] as const,
  target: (target: ChangesTarget) => ['changes', target.kind, target.id, 'summary'] as const,
  /** The key carries the file's counts: when the list changes (a live run), the diff is read again. */
  file: (target: ChangesTarget, file: FileChange) =>
    [
      'changes',
      target.kind,
      target.id,
      target.repo ?? null,
      'file',
      file.path,
      file.old_path,
      file.status,
      file.additions,
      file.deletions,
    ] as const,
  agent: (agentId: string, projectId?: string) =>
    ['changes', 'agent', agentId, projectId ?? null] as const,
}

const base = (target: ChangesTarget) => `/api/${target.kind}s/${target.id}/changes`

export function useChanges(target: ChangesTarget, enabled = true) {
  return useQuery({
    queryKey: changesKeys.target(target),
    queryFn: () => api.get<Changes>(base(target)),
    enabled,
    // A live run keeps changing its folder.
    refetchInterval: (q) => (q.state.data?.live ? 5000 : false),
  })
}

export function useChangesFile(
  target: ChangesTarget,
  file: FileChange,
  enabled: boolean,
  live = false,
) {
  const params = new URLSearchParams({ path: file.path })
  if (file.old_path) params.set('old_path', file.old_path)
  if (target.repo) params.set('repo', target.repo)
  return useQuery({
    queryKey: changesKeys.file(target, file),
    queryFn: () => api.get<FileDiff>(`${base(target)}/file?${params.toString()}`),
    enabled,
    // The files of a finished run never change; a live run's are re-read with the list.
    staleTime: 30_000,
    refetchInterval: live ? 5000 : false,
  })
}

/** Lines of the final version of a file, to widen the context between hunks. */
export function fetchContextLines(
  target: ChangesTarget,
  path: string,
  start: number,
  end: number,
): Promise<DiffLine[]> {
  const params = new URLSearchParams({ path, start: String(start), end: String(end) })
  if (target.repo) params.set('repo', target.repo)
  return api
    .get<{ lines: DiffLine[] }>(`${base(target)}/lines?${params.toString()}`)
    .then((result) => result.lines)
}

export function useAgentChanges(agentId: string, projectId?: string) {
  const params = new URLSearchParams()
  if (projectId) params.set('project_id', projectId)
  const text = params.toString()
  return useQuery({
    queryKey: changesKeys.agent(agentId, projectId),
    queryFn: () =>
      api.get<AgentChangeRun[]>(`/api/agents/${agentId}/changes${text ? `?${text}` : ''}`),
  })
}
