import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

/** Pull requests, SSH keys and tokens for GitHub and GitLab (phase 12, block 6). */

export type PullState = 'open' | 'closed' | 'merged'
export type CheckState = 'success' | 'failure' | 'pending' | 'neutral'
export type MergeMethod = 'merge' | 'squash' | 'rebase'

export interface PullRequest {
  number: number
  title: string
  state: PullState
  draft: boolean
  author: string
  head: string
  base: string
  url: string
  created_at: string | null
  updated_at: string | null
  /** Null: the host has not worked it out yet. */
  mergeable: boolean | null
}

export interface PullDetail extends PullRequest {
  body: string
  checks: { name: string; state: CheckState; url: string }[]
  checks_state: CheckState | null
  reviews: { author: string; state: string }[]
  comments: { author: string; body: string; created_at: string | null }[]
}

export interface ForgeInfo {
  kind: 'github' | 'gitlab' | null
  host: string | null
  remote: string | null
  has_token: boolean
}

export interface RepoPull {
  repo_id: string
  name: string
  status: 'created' | 'nothing' | 'failed'
  pull: PullRequest | null
  error_code: string | null
  message: string
}

export interface SshKey {
  name: string
  path: string
  type: string
  comment: string
  fingerprint: string
  public: string
  orphan: boolean
}

export interface Connection {
  ok: boolean
  user: string | null
  message: string
}

const repoBase = (repoId: string) => ['git', 'repo', repoId] as const

export const forgeKeys = {
  info: (repoId: string) => [...repoBase(repoId), 'forge'] as const,
  pulls: (repoId: string, state: string) => [...repoBase(repoId), 'pulls', state] as const,
  pull: (repoId: string, number: number | null) => [...repoBase(repoId), 'pull', number] as const,
  keys: ['git', 'ssh-keys'] as const,
  token: (host: string) => ['git', 'forge-token', host] as const,
}

export function useForgeInfo(repoId: string) {
  return useQuery({
    queryKey: forgeKeys.info(repoId),
    queryFn: () => api.get<ForgeInfo>(`/api/repos/${repoId}/forge`),
  })
}

export function usePulls(repoId: string, state: 'open' | 'closed' | 'all', enabled: boolean) {
  return useQuery({
    queryKey: forgeKeys.pulls(repoId, state),
    queryFn: () => api.get<PullRequest[]>(`/api/repos/${repoId}/pulls?state=${state}`),
    enabled,
    retry: false,
  })
}

export function usePull(repoId: string, number: number | null) {
  return useQuery({
    queryKey: forgeKeys.pull(repoId, number),
    queryFn: () => api.get<PullDetail>(`/api/repos/${repoId}/pulls/${number}`),
    enabled: number !== null,
    retry: false,
  })
}

/** An action on a pull request: the list and the detail are read again afterwards. */
function usePullMutation<TBody, TResult = void>(
  repoId: string,
  run: (body: TBody) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSettled: () =>
      void queryClient
        .invalidateQueries({ queryKey: [...repoBase(repoId), 'pulls'] })
        .then(() => queryClient.invalidateQueries({ queryKey: [...repoBase(repoId), 'pull'] })),
  })
}

export function useCreatePull(repoId: string) {
  return usePullMutation(
    repoId,
    (body: { title: string; body: string; head: string; base: string; draft: boolean }) =>
      api.post<PullRequest>(`/api/repos/${repoId}/pulls`, body),
  )
}

export function useMergePull(repoId: string) {
  return usePullMutation(repoId, ({ number, method }: { number: number; method: MergeMethod }) =>
    api.post<void>(`/api/repos/${repoId}/pulls/${number}/merge`, { method }),
  )
}

export function usePullAction(repoId: string) {
  return usePullMutation(
    repoId,
    ({ number, action }: { number: number; action: 'close' | 'reopen' | 'update-branch' }) =>
      api.post<void>(`/api/repos/${repoId}/pulls/${number}/${action}`, {}),
  )
}

export function useTaskPulls(taskId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { draft: boolean }) =>
      api.post<RepoPull[]>(`/api/tasks/${taskId}/pulls`, { ...body, push: true }),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['git'] }),
  })
}

// ----------------------------------------------------------------------------- keys and tokens
export function useSshKeys() {
  return useQuery({
    queryKey: forgeKeys.keys,
    queryFn: () => api.get<SshKey[]>('/api/git/ssh-keys'),
  })
}

export function useGenerateKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; email: string; passphrase: string }) =>
      api.post<SshKey>('/api/git/ssh-keys', body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: forgeKeys.keys }),
  })
}

export function useTestConnection() {
  return useMutation({
    mutationFn: (body: { host: string; user?: string }) =>
      api.post<Connection>('/api/git/test-connection', body),
  })
}

export function useTokenState(host: string) {
  return useQuery({
    queryKey: forgeKeys.token(host),
    queryFn: () =>
      api.get<{ has_token: boolean }>(`/api/git/forge-token?host=${encodeURIComponent(host)}`),
    enabled: Boolean(host),
  })
}

export function useSaveToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { host: string; token: string }) =>
      api.post<void>('/api/git/forge-token', body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['git'] }),
  })
}

// ----------------------------------------------------------------------------- global config
export function useGlobalConfig() {
  return useQuery({
    queryKey: ['git', 'config', 'global'] as const,
    queryFn: () => api.get<Record<string, { global?: string | null }>>('/api/git/config'),
  })
}

export function useSetGlobalConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { key: string; value: string | null }) =>
      api.put<void>('/api/git/config', { scope: 'global', ...body }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['git', 'config'] }),
  })
}
