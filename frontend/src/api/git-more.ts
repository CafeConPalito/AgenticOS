import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Changes } from './changes'
import type { JobState } from './git'
import { useRepoMutation } from './git'
import type { OpResult } from './git-integration'

/** The rest of the Git tab (phase 12, block 4): stash, tags, remotes, submodules, LFS,
 * worktrees, upkeep, settings, the git terminal and cloning. */

export interface StashEntry {
  index: number
  ref: string
  sha: string
  message: string
  date: string
  has_untracked: boolean
}

export interface TagInfo {
  name: string
  sha: string
  annotated: boolean
  message: string
  date: string | null
}

export interface Reachability {
  ok: boolean
  error_code: string | null
  message: string
  branches: number
}

export type SubmoduleState = 'ok' | 'not_initialized' | 'modified' | 'conflict'

export interface SubmoduleInfo {
  path: string
  sha: string
  describe: string
  state: SubmoduleState
  url: string
}

export interface LfsState {
  installed: boolean
  used: boolean
  patterns: string[]
  files: number
}

export interface WorktreeInfo {
  path: string
  head: string | null
  branch: string | null
  main: boolean
  locked: boolean
  prunable: boolean
  task: boolean
}

export interface CleanPreview {
  files: string[]
  folders: string[]
}

export interface Verification {
  ok: boolean
  problems: string[]
}

export interface RepoSize {
  loose: string
  packed: string
  garbage: string
}

export type ConfigScope = 'local' | 'global'
/** The usual settings: key → value of each scope (null when it is not set there). */
export type CommonConfig = Record<string, Partial<Record<ConfigScope, string | null>>>

export interface CloneStarted {
  job: JobState
  path: string
}

const base = (repoId: string) => ['git', 'repo', repoId] as const

export const moreKeys = {
  stashes: (repoId: string) => [...base(repoId), 'stashes'] as const,
  tags: (repoId: string) => [...base(repoId), 'tags'] as const,
  submodules: (repoId: string) => [...base(repoId), 'submodules'] as const,
  lfs: (repoId: string) => [...base(repoId), 'lfs'] as const,
  worktrees: (repoId: string) => [...base(repoId), 'worktrees'] as const,
  clean: (repoId: string, folders: boolean, ignored: boolean) =>
    [...base(repoId), 'clean', folders, ignored] as const,
  overwrites: (repoId: string) => [...base(repoId), 'overwrites'] as const,
  size: (repoId: string) => [...base(repoId), 'size'] as const,
  config: (repoId: string | null) => ['git', 'config', repoId] as const,
}

// ----------------------------------------------------------------------------- stash
export function useStashes(repoId: string) {
  return useQuery({
    queryKey: moreKeys.stashes(repoId),
    queryFn: () => api.get<StashEntry[]>(`/api/repos/${repoId}/stashes`),
  })
}

export function useStashDiff(repoId: string, ref: string | null) {
  return useQuery({
    queryKey: [...moreKeys.stashes(repoId), 'diff', ref] as const,
    queryFn: () =>
      api.get<Changes>(`/api/repos/${repoId}/stashes/diff?ref=${encodeURIComponent(ref ?? '')}`),
    enabled: Boolean(ref),
  })
}

export function usePushStash(repoId: string) {
  return useRepoMutation(repoId, (body: { message?: string; include_untracked: boolean }) =>
    api.post<{ stored: boolean }>(`/api/repos/${repoId}/stashes`, body),
  )
}

export function useApplyStash(repoId: string) {
  return useRepoMutation(repoId, (body: { ref: string; drop: boolean }) =>
    api.post<OpResult>(`/api/repos/${repoId}/stashes/apply`, body),
  )
}

export function useDropStash(repoId: string) {
  return useRepoMutation(repoId, (ref: string) =>
    api.post<void>(`/api/repos/${repoId}/stashes/drop`, { ref, confirm: true }),
  )
}

export function useStashToBranch(repoId: string) {
  return useRepoMutation(repoId, (body: { ref: string; name: string }) =>
    api.post<void>(`/api/repos/${repoId}/stashes/branch`, body),
  )
}

// ----------------------------------------------------------------------------- tags
export function useTags(repoId: string) {
  return useQuery({
    queryKey: moreKeys.tags(repoId),
    queryFn: () => api.get<TagInfo[]>(`/api/repos/${repoId}/tags`),
  })
}

export function useCreateTag(repoId: string) {
  return useRepoMutation(repoId, (body: { name: string; ref?: string; message?: string }) =>
    api.post<void>(`/api/repos/${repoId}/tags`, body),
  )
}

export function useDeleteTag(repoId: string) {
  return useRepoMutation(repoId, (name: string) =>
    api.delete(`/api/repos/${repoId}/tags/${encodeURIComponent(name)}`),
  )
}

/** Publishes the tag on the remote, or (`delete`) removes it from there. */
export function useTagOnRemote(repoId: string) {
  return useRepoMutation(repoId, (body: { name: string; remote?: string; delete?: boolean }) =>
    api.post<JobState>(`/api/repos/${repoId}/tags/remote`, body),
  )
}

// ----------------------------------------------------------------------------- remotes
export function useAddRemote(repoId: string) {
  return useRepoMutation(repoId, (body: { name: string; url: string }) =>
    api.post<void>(`/api/repos/${repoId}/remotes`, body),
  )
}

export function useEditRemote(repoId: string) {
  return useRepoMutation(
    repoId,
    ({ name, ...body }: { name: string; url?: string; rename_to?: string }) =>
      api.patch<void>(`/api/repos/${repoId}/remotes/${encodeURIComponent(name)}`, body),
  )
}

export function useRemoveRemote(repoId: string) {
  return useRepoMutation(repoId, (name: string) =>
    api.delete(`/api/repos/${repoId}/remotes/${encodeURIComponent(name)}`),
  )
}

export function useTestRemote(repoId: string) {
  return useMutation({
    mutationFn: (name: string) =>
      api.post<Reachability>(`/api/repos/${repoId}/remotes/${encodeURIComponent(name)}/test`, {}),
  })
}

/** The commits a forced push would destroy on the remote. */
export function useOverwrites(repoId: string, enabled: boolean) {
  return useQuery({
    queryKey: moreKeys.overwrites(repoId),
    queryFn: () => api.get<string[]>(`/api/repos/${repoId}/push/overwrites`),
    enabled,
    staleTime: 0,
  })
}

export function useForcePush(repoId: string) {
  return useRepoMutation(repoId, (body: { remote?: string; branch?: string }) =>
    api.post<JobState>(`/api/repos/${repoId}/push/force`, { ...body, confirm: true }),
  )
}

// ----------------------------------------------------------------------------- submodules
export function useSubmodules(repoId: string) {
  return useQuery({
    queryKey: moreKeys.submodules(repoId),
    queryFn: () => api.get<SubmoduleInfo[]>(`/api/repos/${repoId}/submodules`),
  })
}

export function useUpdateSubmodules(repoId: string) {
  return useRepoMutation(repoId, (path?: string) =>
    api.post<JobState>(`/api/repos/${repoId}/submodules/update`, { path: path ?? null }),
  )
}

export function useAddSubmodule(repoId: string) {
  return useRepoMutation(repoId, (body: { url: string; path: string }) =>
    api.post<void>(`/api/repos/${repoId}/submodules`, body),
  )
}

export function useRemoveSubmodule(repoId: string) {
  return useRepoMutation(repoId, (path: string) =>
    api.post<void>(`/api/repos/${repoId}/submodules/remove`, { path, confirm: true }),
  )
}

// ----------------------------------------------------------------------------- LFS
export function useLfs(repoId: string) {
  return useQuery({
    queryKey: moreKeys.lfs(repoId),
    queryFn: () => api.get<LfsState>(`/api/repos/${repoId}/lfs`),
  })
}

export function useLfsPattern(repoId: string) {
  return useRepoMutation(repoId, (body: { action: 'track' | 'untrack'; pattern: string }) =>
    api.post<void>(`/api/repos/${repoId}/lfs/${body.action}`, { pattern: body.pattern }),
  )
}

export function useLfsPull(repoId: string) {
  return useRepoMutation(repoId, () => api.post<JobState>(`/api/repos/${repoId}/lfs/pull`, {}))
}

// ----------------------------------------------------------------------------- worktrees
export function useWorktrees(repoId: string) {
  return useQuery({
    queryKey: moreKeys.worktrees(repoId),
    queryFn: () => api.get<WorktreeInfo[]>(`/api/repos/${repoId}/worktrees`),
  })
}

export function useRemoveWorktree(repoId: string) {
  return useRepoMutation(repoId, (body: { path: string; force?: boolean }) =>
    api.post<void>(`/api/repos/${repoId}/worktrees/remove`, body),
  )
}

export function usePruneWorktrees(repoId: string) {
  return useRepoMutation(repoId, () => api.post<void>(`/api/repos/${repoId}/worktrees/prune`, {}))
}

// ----------------------------------------------------------------------------- upkeep
export function useCleanPreview(repoId: string, folders: boolean, ignored: boolean) {
  return useQuery({
    queryKey: moreKeys.clean(repoId, folders, ignored),
    queryFn: () =>
      api.get<CleanPreview>(
        `/api/repos/${repoId}/clean/preview?folders=${folders}&ignored=${ignored}`,
      ),
    staleTime: 0,
  })
}

export function useClean(repoId: string) {
  return useRepoMutation(repoId, (body: { paths: string[]; folders: boolean; ignored: boolean }) =>
    api.post<void>(`/api/repos/${repoId}/clean`, { ...body, confirm: true }),
  )
}

export function useGc(repoId: string) {
  return useRepoMutation(repoId, () => api.post<JobState>(`/api/repos/${repoId}/gc`, {}))
}

export function useVerify(repoId: string) {
  return useMutation({ mutationFn: () => api.get<Verification>(`/api/repos/${repoId}/verify`) })
}

export function useRepoSize(repoId: string) {
  return useQuery({
    queryKey: moreKeys.size(repoId),
    queryFn: () => api.get<RepoSize>(`/api/repos/${repoId}/size`),
  })
}

// ----------------------------------------------------------------------------- settings
export function useRepoConfig(repoId: string) {
  return useQuery({
    queryKey: moreKeys.config(repoId),
    queryFn: () => api.get<CommonConfig>(`/api/repos/${repoId}/config`),
  })
}

export function useSetConfig(repoId: string) {
  return useRepoMutation(
    repoId,
    (body: { scope: ConfigScope; key: string; value: string | null }) =>
      api.put<void>(`/api/repos/${repoId}/config`, body),
  )
}

// ----------------------------------------------------------------------------- terminal
export function useOpenShell(repoId: string) {
  return useMutation({
    mutationFn: () => api.post<{ shell_id: string }>(`/api/repos/${repoId}/shell`, {}),
  })
}

export function closeShell(shellId: string) {
  return api.delete(`/api/git/shells/${shellId}`)
}

// ----------------------------------------------------------------------------- clone, init
export function useClone() {
  return useMutation({
    mutationFn: (body: { url: string; parent_folder: string; name?: string }) =>
      api.post<CloneStarted>('/api/git/clone', body),
  })
}

export function useInitRepo(projectId: string) {
  return useRepoMutation(projectId, (body: { branch: string; path?: string }) =>
    api.post<{ path: string }>(`/api/projects/${projectId}/repos/init`, body),
  )
}
