import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { api } from '@/lib/api'
import { changesKeys } from './changes'

/** The Git tab of a project (phase 12): state, history, branches, staging and network jobs. */

export type Operation = 'merge' | 'rebase' | 'cherry-pick' | 'revert' | 'bisect'
export type FileKind = 'changed' | 'renamed' | 'unmerged' | 'untracked'

export interface StatusFile {
  path: string
  orig_path: string | null
  /** git's letter: M, A, D, R, C, T, U or ? (untracked). */
  status: string
  kind: FileKind
}

export interface RepoStatus {
  repo_id: string | null
  /** Null while detached. */
  branch: string | null
  head: string | null
  detached: boolean
  upstream: string | null
  ahead: number
  behind: number
  staged: StatusFile[]
  unstaged: StatusFile[]
  conflicts: StatusFile[]
  stashes: number
  operation: Operation | null
  last_fetch: string | null
  clean: boolean
  empty: boolean
}

export interface RepoOverview {
  repo_id: string
  name: string
  path: string
  rel_path: string | null
  linked: boolean
  missing: boolean
  base_branch: string | null
  status: RepoStatus | null
  error: string | null
}

export interface CommitInfo {
  sha: string
  short: string
  parents: string[]
  author: string
  email: string
  date: string
  subject: string
  refs: string[]
  agent_name: string | null
  task_code: string | null
  run_id: string | null
}

export interface CommitPage {
  commits: CommitInfo[]
  more: boolean
}

export interface CommitDetail extends CommitInfo {
  body: string
}

export interface BranchInfo {
  name: string
  sha: string
  short: string
  current: boolean
  remote: boolean
  upstream: string | null
  ahead: number
  behind: number
  base_ahead: number | null
  base_behind: number | null
  last_commit: string
  subject: string
  task_id: string | null
  task_code: string | null
  task_title: string | null
  task_status: string | null
  integrated: boolean
}

export interface BlameGroup {
  start: number
  lines: number
  sha: string
  short: string
  author: string
  date: string
  summary: string
  text: string[]
  agent_name: string | null
  task_code: string | null
}

export interface RemoteInfo {
  name: string
  fetch_url: string
  push_url: string
}

export type JobStatus = 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface JobState {
  id: string
  repo_id: string
  kind: string
  status: JobStatus
  phase: string
  percent: number | null
  message: string
  error_code: string | null
  started_at: string
  ended_at: string | null
}

export interface BatchItem {
  repo_id: string
  ok: boolean
  job: JobState | null
  sha: string | null
  error_code: string | null
  error: string | null
}

export interface LineRef {
  kind: 'add' | 'del'
  no: number
}

export type PullMode = 'ff_only' | 'merge' | 'rebase'

export interface HistoryFilters {
  /** One ref (default: the current branch). */
  ref?: string
  allRefs?: boolean
  author?: string
  grep?: string
  search?: string
  path?: string
}

export const gitKeys = {
  all: ['git'] as const,
  overview: (projectId: string) => ['git', 'overview', projectId] as const,
  repo: (repoId: string) => ['git', 'repo', repoId] as const,
  status: (repoId: string) => ['git', 'repo', repoId, 'status'] as const,
  branches: (repoId: string) => ['git', 'repo', repoId, 'branches'] as const,
  remotes: (repoId: string) => ['git', 'repo', repoId, 'remotes'] as const,
  history: (repoId: string, filters: HistoryFilters) =>
    ['git', 'repo', repoId, 'history', filters] as const,
  commit: (repoId: string, sha: string) => ['git', 'repo', repoId, 'commit', sha] as const,
  blame: (repoId: string, path: string, rev?: string) =>
    ['git', 'repo', repoId, 'blame', path, rev ?? null] as const,
}

/** Everything that was read about a repository is read again (after it changed). */
export function invalidateRepo(queryClient: QueryClient, repoId: string) {
  void queryClient.invalidateQueries({ queryKey: gitKeys.repo(repoId) })
  // Diffs of this repository's work tree and commits (targets of kind `repo`).
  void queryClient.invalidateQueries({ queryKey: [...changesKeys.all, 'repo', repoId] })
  void queryClient.invalidateQueries({ queryKey: ['git', 'overview'] })
}

// ----------------------------------------------------------------------------- reads
export function useGitOverview(projectId: string) {
  return useQuery({
    queryKey: gitKeys.overview(projectId),
    queryFn: () => api.get<RepoOverview[]>(`/api/projects/${projectId}/git/overview`),
  })
}

export function useRepoStatus(repoId: string | undefined) {
  return useQuery({
    queryKey: gitKeys.status(repoId ?? ''),
    queryFn: () => api.get<RepoStatus>(`/api/repos/${repoId}/status`),
    enabled: Boolean(repoId),
  })
}

export function useBranches(repoId: string | undefined) {
  return useQuery({
    queryKey: gitKeys.branches(repoId ?? ''),
    queryFn: () => api.get<BranchInfo[]>(`/api/repos/${repoId}/branches`),
    enabled: Boolean(repoId),
  })
}

export function useRemotes(repoId: string | undefined) {
  return useQuery({
    queryKey: gitKeys.remotes(repoId ?? ''),
    queryFn: () => api.get<RemoteInfo[]>(`/api/repos/${repoId}/remotes`),
    enabled: Boolean(repoId),
  })
}

export const HISTORY_PAGE = 200

/** The history in pages of 200, newest first; the next page is asked by position (`skip`). */
export function useHistory(repoId: string | undefined, filters: HistoryFilters) {
  return useInfiniteQuery({
    queryKey: gitKeys.history(repoId ?? '', filters),
    enabled: Boolean(repoId),
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ skip: String(pageParam), limit: String(HISTORY_PAGE) })
      if (filters.ref) params.set('ref', filters.ref)
      if (filters.allRefs) params.set('all_refs', 'true')
      if (filters.author) params.set('author', filters.author)
      if (filters.grep) params.set('grep', filters.grep)
      if (filters.search) params.set('search', filters.search)
      if (filters.path) params.set('path', filters.path)
      return api.get<CommitPage>(`/api/repos/${repoId}/log?${params.toString()}`)
    },
    getNextPageParam: (last, pages) =>
      last.more ? pages.reduce((sum, page) => sum + page.commits.length, 0) : undefined,
  })
}

export function useCommit(repoId: string, sha: string | null) {
  return useQuery({
    queryKey: gitKeys.commit(repoId, sha ?? ''),
    queryFn: () => api.get<CommitDetail>(`/api/repos/${repoId}/commits/${sha}`),
    enabled: Boolean(sha),
    staleTime: Infinity, // a commit never changes
  })
}

export function useBlame(repoId: string, path: string | null, rev?: string) {
  const params = new URLSearchParams({ path: path ?? '' })
  if (rev) params.set('rev', rev)
  return useQuery({
    queryKey: gitKeys.blame(repoId, path ?? '', rev),
    queryFn: () => api.get<BlameGroup[]>(`/api/repos/${repoId}/blame?${params.toString()}`),
    enabled: Boolean(path),
  })
}

// ----------------------------------------------------------------------------- writes
/** A mutation on a repository: when it ends, what was read about it is read again. */
function useRepoMutation<TBody, TResult = void>(
  repoId: string,
  run: (body: TBody) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSettled: () => invalidateRepo(queryClient, repoId),
  })
}

export function useStage(repoId: string) {
  return useRepoMutation(repoId, (paths: string[]) =>
    api.post<void>(`/api/repos/${repoId}/stage`, { paths }),
  )
}

export function useUnstage(repoId: string) {
  return useRepoMutation(repoId, (paths: string[]) =>
    api.post<void>(`/api/repos/${repoId}/unstage`, { paths }),
  )
}

export function useDiscard(repoId: string) {
  return useRepoMutation(repoId, (paths: string[]) =>
    api.post<void>(`/api/repos/${repoId}/discard`, { paths, confirm: true }),
  )
}

export interface ApplyBody {
  action: 'stage' | 'unstage' | 'discard'
  path: string
  lines: LineRef[]
}

export function useApplyLines(repoId: string) {
  return useRepoMutation(repoId, (body: ApplyBody) =>
    api.post<void>(`/api/repos/${repoId}/apply`, { ...body, hunks: [], confirm: true }),
  )
}

export interface CommitBody {
  message: string
  amend?: boolean
  no_verify?: boolean
}

export function useCommitStaged(repoId: string) {
  return useRepoMutation(repoId, (body: CommitBody) =>
    api.post<CommitDetail>(`/api/repos/${repoId}/commit`, body),
  )
}

export function useCreateBranch(repoId: string) {
  return useRepoMutation(repoId, (body: { name: string; start?: string; switch?: boolean }) =>
    api.post<void>(`/api/repos/${repoId}/branches`, body),
  )
}

export function useSwitchBranch(repoId: string) {
  return useRepoMutation(repoId, (name: string) =>
    api.post<void>(`/api/repos/${repoId}/switch`, { name }),
  )
}

export function useRenameBranch(repoId: string) {
  return useRepoMutation(repoId, (body: { old: string; new: string }) =>
    api.post<void>(`/api/repos/${repoId}/branches/rename`, body),
  )
}

export function useDeleteBranches(repoId: string) {
  return useRepoMutation(repoId, (body: { names: string[]; force?: boolean }) =>
    api.post<{ failed: Record<string, string> }>(`/api/repos/${repoId}/branches/delete`, {
      ...body,
      confirm: Boolean(body.force),
    }),
  )
}

// ----------------------------------------------------------------------------- network jobs
export function useFetch(repoId: string) {
  return useMutation({
    mutationFn: () => api.post<JobState>(`/api/repos/${repoId}/fetch`, {}),
  })
}

export function usePull(repoId: string) {
  return useMutation({
    mutationFn: (mode?: PullMode) => api.post<JobState>(`/api/repos/${repoId}/pull`, { mode }),
  })
}

export function usePush(repoId: string) {
  return useMutation({
    mutationFn: () => api.post<JobState>(`/api/repos/${repoId}/push`, {}),
  })
}

export function useCancelJob() {
  return useMutation({
    mutationFn: (jobId: string) => api.delete(`/api/git/jobs/${jobId}`),
  })
}

export interface BatchRequest {
  action: 'fetch' | 'pull' | 'push' | 'switch' | 'create_branch' | 'commit'
  repo_ids: string[]
  name?: string
  message?: string
}

export function useBatch(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: BatchRequest) =>
      api.post<BatchItem[]>(`/api/projects/${projectId}/git/batch`, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: gitKeys.all }),
  })
}
