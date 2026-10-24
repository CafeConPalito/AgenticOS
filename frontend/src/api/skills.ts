import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, getApiBaseUrl } from '@/lib/api'
import type { DiffLine, FileChange, Hunk } from '@/api/changes'
import type { KnowledgeLevel, KnowledgeScope } from '@/api/knowledge'

/** Phase 17: the skill library, its use in the runs, the agents' proposals, the public
 * registries and the usage statistics. */

export type SkillOrigin = 'user' | 'agent' | 'import' | 'registry'
export type SkillMode = 'auto' | 'always' | 'never'
export type LoadedVia = 'context' | 'tool' | 'native'
export type VersionAuthorKind = 'user' | 'agent' | 'import' | 'registry' | 'restore'

export interface Skill {
  id: string
  name: string
  description: string
  scope: KnowledgeScope
  project_id: string | null
  agent_id: string | null
  enabled: boolean
  review: 'none' | 'proposed'
  origin: SkillOrigin
  version: number | null
  tokens: number
  files: number
  executables: number
  model_invocable: boolean
  used: number
  last_used: string | null
  created_at: string
  updated_at: string
}

export interface SkillFile {
  path: string
  size: number
  executable: boolean
}

export interface SkillDetail extends Skill {
  body: string
  header: Record<string, unknown>
  file_list: SkillFile[]
  versions: number
}

export interface SkillVersion {
  id: string
  number: number
  status: 'accepted' | 'proposed' | 'rejected'
  description: string
  tokens: number
  files: number
  note: string
  author: {
    kind: VersionAuthorKind
    label: string
    agent_id: string | null
    run_id: string | null
    task_id: string | null
    task_title: string
  }
  base_version_id: string | null
  restored_from_id: string | null
  created_at: string
  decided_at: string | null
  current: boolean
}

export interface DiffFile {
  change: FileChange
  diff: { path: string; hunks: Hunk[]; binary: boolean; too_large: boolean }
}

export interface SkillDiff {
  from_version: number | null
  to_version: number
  files: DiffFile[]
}

export type { DiffLine }

/** A file sent by the editor: text, or anything else in base64. `null` removes it. */
export type FileInput = { text: string } | { base64: string }

export interface ImportResult {
  path: string
  skill: Skill | null
  renamed_to: string | null
  error_code: string | null
  message: string | null
}

export interface CliSkill {
  source: 'claude_user' | 'claude_project' | 'agy_global' | 'agy_project'
  path: string
  name: string
  description: string
  project_id: string | null
  project_name: string
  imported: boolean
  error: string
}

export interface SkillModeRow {
  skill: Skill
  mode: SkillMode
  effective: SkillMode
  set_by: 'stage' | 'agent' | 'default'
}

export type ExcludedReason = 'never_stage' | 'never_agent' | 'manual_only' | 'below_floor'

export interface TryResult {
  method: 'vector' | 'words' | 'none'
  always: Skill[]
  candidates: { skill: Skill; rank: number; score: number | null }[]
  excluded: { skill: Skill; reason: ExcludedReason }[]
  section: string
}

export interface RunSkill {
  skill_id: string
  skill_name: string
  offered: 'always' | 'candidate' | 'requested'
  rank: number
  score: number | null
  loaded_via: LoadedVia | null
  loaded_at: string | null
  version: number | null
}

export interface Proposal {
  skill: Skill
  version: SkillVersion
  new_skill: boolean
  suggested_scope: string
  body: string
  header: Record<string, unknown>
  files: SkillFile[]
  executables: string[]
  inbox_item_id: string | null
}

export interface SkillSettings {
  candidates: number
  index_tokens: number
  always_tokens: number
  words_floor: number
  proposals_enabled: boolean
  proposals_per_run: number
  registries: Record<string, boolean>
  skillsmp_key_set: boolean
}

export interface Registry {
  id: string
  title: string
  enabled: boolean
  switchable: boolean
  default_enabled: boolean
  has_popular: boolean
}

export interface RegistryCard {
  source: string
  ref: string
  name: string
  description: string
  author: string
  installs: number | null
  stars: number | null
  updated_at: string | null
  category: string
  url: string
  installed_skill_id: string | null
}

export interface Listing {
  cards: RegistryCard[]
  errors: Record<string, string>
  attribution: string
}

export interface RegistryPreview {
  id: string
  card: RegistryCard
  revision: string
  repo_url: string
  path: string
  license: string
  security: Record<string, unknown>
  name: string
  body: string
  header: Record<string, unknown>
  files: SkillFile[]
  executables: string[]
}

export interface SkillOriginInfo {
  source: string
  title: string
  ref: string
  repo_url: string
  revision: string
  latest_revision: string
  update_available: boolean
  license: string
  security: Record<string, unknown>
  checked_at: string | null
}

export type StatsGroup =
  'agent' | 'team' | 'project' | 'pipeline' | 'stage' | 'cli' | 'account' | 'model'

export interface StatsRow {
  skill_id: string
  name: string
  scope: KnowledgeScope
  origin: SkillOrigin
  group_key: string | null
  group_label: string
  offered: number
  loaded: number
  rate: number | null
  runs: number
  tasks: number
  done: number
  failed: number
  approved: number
  rejected: number
  avg_cost: number | null
  avg_tokens: number | null
  last_used: string | null
  via_context: number
  via_tool: number
  via_native: number
}

export interface StatsRun {
  run_id: string
  started_at: string
  skill_id: string
  skill_name: string
  version: number | null
  offered: string
  loaded_via: LoadedVia | null
  agent_name: string
  project_name: string
  stage_name: string
  pipeline_name: string
  cli: string
  model: string
  account_label: string
  status: string
  verdict: string | null
  cost_usd: number | null
  task_id: string | null
}

/** The filters of the «Uso» view, as query parameters (kept in the URL). */
export type StatsFilters = Partial<
  Record<
    | 'from'
    | 'to'
    | 'agent_id'
    | 'team_id'
    | 'project_id'
    | 'pipeline_id'
    | 'stage_id'
    | 'cli'
    | 'account_id'
    | 'model'
    | 'scope'
    | 'origin'
    | 'via'
    | 'unused'
    | 'skill_id',
    string
  >
>

export const skillKeys = {
  all: ['skills'] as const,
  level: (level: KnowledgeLevel | 'all') => ['skills', 'list', level] as const,
  skill: (id: string) => ['skills', 'one', id] as const,
  versions: (id: string) => ['skills', 'versions', id] as const,
  diff: (id: string, from: string | null, to: string | null) =>
    ['skills', 'diff', id, from, to] as const,
  origin: (id: string) => ['skills', 'origin', id] as const,
  cliScan: ['skills', 'cli-scan'] as const,
  agentModes: (id: string) => ['skills', 'modes', 'agent', id] as const,
  stageModes: (id: string) => ['skills', 'modes', 'stage', id] as const,
  run: (id: string) => ['skills', 'run', id] as const,
  proposals: ['skills', 'proposals'] as const,
  proposal: (id: string) => ['skills', 'proposal', id] as const,
  settings: ['skills', 'settings'] as const,
  registries: ['skills', 'registries'] as const,
  popular: (source: string | null) => ['skills', 'popular', source] as const,
  search: (q: string, source: string | null) => ['skills', 'search', q, source] as const,
  stats: (params: string) => ['skills', 'stats', params] as const,
  daily: (params: string) => ['skills', 'daily', params] as const,
  statsRuns: (params: string) => ['skills', 'stats-runs', params] as const,
}

/** A file path in a URL: each segment encoded («run#1.py», «a?b.md»…), the slashes kept. */
export const encodePath = (path: string) => path.split('/').map(encodeURIComponent).join('/')

function levelQuery(level: KnowledgeLevel | 'all'): string {
  if (level === 'all') return ''
  const params = new URLSearchParams({ scope: level.scope })
  if (level.projectId) params.set('project_id', level.projectId)
  if (level.agentId) params.set('agent_id', level.agentId)
  return `?${params}`
}

export function levelBody(level: KnowledgeLevel) {
  return {
    scope: level.scope,
    project_id: level.projectId ?? null,
    agent_id: level.agentId ?? null,
  }
}

function useInvalidateSkills() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: skillKeys.all })
}

// ------------------------------------------------------------------- library
export function useSkills(level: KnowledgeLevel | 'all') {
  return useQuery({
    queryKey: skillKeys.level(level),
    queryFn: () => api.get<Skill[]>(`/api/skills${levelQuery(level)}`),
  })
}

export function useSkill(id: string | null) {
  return useQuery({
    queryKey: skillKeys.skill(id ?? ''),
    queryFn: () => api.get<SkillDetail>(`/api/skills/${id}`),
    enabled: id !== null,
  })
}

export interface SkillInput {
  name: string
  description: string
  body: string
  files?: Record<string, FileInput>
  note?: string
}

export function useCreateSkill(level: KnowledgeLevel) {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (input: SkillInput) =>
      api.post<SkillDetail>('/api/skills', { ...levelBody(level), ...input }),
    onSuccess: invalidate,
  })
}

export interface SkillEditInput {
  name?: string
  description?: string
  body?: string
  files?: Record<string, FileInput | null>
  note?: string
}

export function useSaveSkill(id: string) {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (input: SkillEditInput) =>
      api.post<SkillDetail>(`/api/skills/${id}/versions`, input),
    onSuccess: invalidate,
  })
}

export function useUpdateSkill() {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: ({
      id,
      ...patch
    }: { id: string; enabled?: boolean } & Partial<ReturnType<typeof levelBody>>) =>
      api.patch<SkillDetail>(`/api/skills/${id}`, patch),
    onSuccess: invalidate,
  })
}

export function useDeleteSkill() {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/skills/${id}`),
    onSuccess: invalidate,
  })
}

export function useSkillVersions(id: string | null) {
  return useQuery({
    queryKey: skillKeys.versions(id ?? ''),
    queryFn: () => api.get<SkillVersion[]>(`/api/skills/${id}/versions`),
    enabled: id !== null,
  })
}

export function useSkillDiff(id: string | null, from: string | null, to: string | null) {
  const params = new URLSearchParams()
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  return useQuery({
    queryKey: skillKeys.diff(id ?? '', from, to),
    queryFn: () => api.get<SkillDiff>(`/api/skills/${id}/diff?${params}`),
    enabled: id !== null,
  })
}

export function useRestoreVersion(id: string) {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (versionId: string) =>
      api.post<SkillDetail>(`/api/skills/${id}/restore/${versionId}`),
    onSuccess: invalidate,
  })
}

/** The text of one file of a version (the current one by default). */
export async function fetchSkillFile(id: string, path: string, version?: string): Promise<string> {
  const base = await getApiBaseUrl()
  const query = version ? `?version=${encodeURIComponent(version)}` : ''
  const response = await fetch(`${base}/api/skills/${id}/files/${encodePath(path)}${query}`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.text()
}

export async function exportUrl(id: string): Promise<string> {
  return `${await getApiBaseUrl()}/api/skills/${id}/export`
}

export function useImportSkill(level: KnowledgeLevel) {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (path: string) =>
      api.post<ImportResult>('/api/skills/import', { ...levelBody(level), path }),
    onSuccess: invalidate,
  })
}

export function useCliSkills(enabled: boolean) {
  return useQuery({
    queryKey: skillKeys.cliScan,
    queryFn: () => api.get<CliSkill[]>('/api/skills/cli-scan'),
    enabled,
  })
}

export function useImportCliSkills() {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (items: ({ path: string } & ReturnType<typeof levelBody>)[]) =>
      api.post<ImportResult[]>('/api/skills/cli-import', { items }),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- use
export function useAgentSkillModes(agentId: string) {
  return useQuery({
    queryKey: skillKeys.agentModes(agentId),
    queryFn: () => api.get<SkillModeRow[]>(`/api/agents/${agentId}/skill-modes`),
  })
}

export function useStageSkillModes(stageId: string | null) {
  return useQuery({
    queryKey: skillKeys.stageModes(stageId ?? ''),
    queryFn: () => api.get<SkillModeRow[]>(`/api/stages/${stageId}/skill-modes`),
    enabled: stageId !== null,
  })
}

export function useSetSkillModes(target: { agentId: string } | { stageId: string }) {
  const invalidate = useInvalidateSkills()
  const path =
    'agentId' in target
      ? `/api/agents/${target.agentId}/skill-modes`
      : `/api/stages/${target.stageId}/skill-modes`
  return useMutation({
    mutationFn: (modes: Record<string, SkillMode>) => api.put<SkillModeRow[]>(path, { modes }),
    onSuccess: invalidate,
  })
}

export function useTrySkills() {
  return useMutation({
    mutationFn: (input: {
      text: string
      agent_id?: string | null
      project_id?: string | null
      stage_id?: string | null
    }) => api.post<TryResult>('/api/skills/try', input),
  })
}

export function useRunSkills(runId: string) {
  return useQuery({
    queryKey: skillKeys.run(runId),
    queryFn: () => api.get<RunSkill[]>(`/api/runs/${runId}/skills`),
  })
}

// ------------------------------------------------------------------- proposals
export function useProposals() {
  return useQuery({
    queryKey: skillKeys.proposals,
    queryFn: () => api.get<Proposal[]>('/api/skills/proposals/pending'),
  })
}

export function useProposal(versionId: string | null) {
  return useQuery({
    queryKey: skillKeys.proposal(versionId ?? ''),
    queryFn: () => api.get<Proposal>(`/api/skills/proposals/${versionId}`),
    enabled: versionId !== null,
  })
}

export interface AcceptSkillInput {
  opened_files: string[]
  name?: string
  description?: string
  body?: string
  scope?: KnowledgeScope
  project_id?: string | null
  agent_id?: string | null
}

function useInvalidateInbox() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: skillKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['inbox'] }),
    ])
}

export function useAcceptSkillProposal() {
  const invalidate = useInvalidateInbox()
  return useMutation({
    mutationFn: ({ versionId, ...input }: AcceptSkillInput & { versionId: string }) =>
      api.post<SkillDetail>(`/api/skills/proposals/${versionId}/accept`, input),
    onSuccess: invalidate,
  })
}

export function useRejectSkillProposal() {
  const invalidate = useInvalidateInbox()
  return useMutation({
    mutationFn: ({ versionId, reason }: { versionId: string; reason: string }) =>
      api.post<void>(`/api/skills/proposals/${versionId}/reject`, { reason }),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- settings
export function useSkillSettings() {
  return useQuery({
    queryKey: skillKeys.settings,
    queryFn: () => api.get<SkillSettings>('/api/settings/skills'),
  })
}

export function useSaveSkillSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (
      values: Partial<Omit<SkillSettings, 'skillsmp_key_set'>> & { skillsmp_key?: string },
    ) => api.put<SkillSettings>('/api/settings/skills', values),
    onSuccess: (data) => {
      queryClient.setQueryData(skillKeys.settings, data)
      void queryClient.invalidateQueries({ queryKey: ['skills', 'popular'] })
      void queryClient.invalidateQueries({ queryKey: ['skills', 'search'] })
      void queryClient.invalidateQueries({ queryKey: skillKeys.registries })
    },
  })
}

// ------------------------------------------------------------------- registries
export function useRegistries() {
  return useQuery({
    queryKey: skillKeys.registries,
    queryFn: () => api.get<Registry[]>('/api/skills/registries'),
  })
}

export function usePopularSkills(source: string | null) {
  return useQuery({
    queryKey: skillKeys.popular(source),
    queryFn: () =>
      api.get<Listing>(
        `/api/skills/registries/popular${source ? `?source=${encodeURIComponent(source)}` : ''}`,
      ),
    staleTime: 5 * 60_000,
  })
}

export function useSearchSkills(q: string, source: string | null) {
  const params = new URLSearchParams({ q })
  if (source) params.set('source', source)
  return useQuery({
    queryKey: skillKeys.search(q, source),
    queryFn: () => api.get<Listing>(`/api/skills/registries/search?${params}`),
    enabled: q.trim().length > 0,
    staleTime: 5 * 60_000,
  })
}

export function usePreviewSkill() {
  return useMutation({
    mutationFn: (card: { source: string; ref: string }) =>
      api.post<RegistryPreview>('/api/skills/registries/preview', {
        source: card.source,
        ref: card.ref,
      }),
  })
}

export async function fetchPreviewFile(previewId: string, path: string): Promise<string> {
  const base = await getApiBaseUrl()
  const response = await fetch(
    `${base}/api/skills/registries/previews/${previewId}/files/${encodePath(path)}`,
  )
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.text()
}

export function useInstallSkill() {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (
      input: { preview_id: string; opened_files: string[] } & ReturnType<typeof levelBody>,
    ) =>
      api.post<{ skill: SkillDetail; renamed_to: string | null }>(
        '/api/skills/registries/install',
        input,
      ),
    onSuccess: invalidate,
  })
}

export function useSkillOrigin(id: string | null, enabled = true) {
  return useQuery({
    queryKey: skillKeys.origin(id ?? ''),
    queryFn: () => api.get<SkillOriginInfo | null>(`/api/skills/${id}/origin`),
    enabled: id !== null && enabled,
  })
}

export function useCheckUpdates() {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: () => api.post<Record<string, string>>('/api/skills/updates/check'),
    onSuccess: invalidate,
  })
}

export function useUpdatePreview() {
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ preview: RegistryPreview; files: DiffFile[] }>(`/api/skills/${id}/update-preview`),
  })
}

export function useApplyUpdate(id: string) {
  const invalidate = useInvalidateSkills()
  return useMutation({
    mutationFn: (input: { preview_id: string; opened_files: string[] }) =>
      api.post<SkillDetail>(`/api/skills/${id}/update`, input),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- statistics
export function statsQuery(
  filters: StatsFilters,
  extra: Record<string, string | undefined> = {},
): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries({ ...filters, ...extra })) {
    if (value) params.set(key, value)
  }
  return params.toString()
}

export function useSkillStats(query: string) {
  return useQuery({
    queryKey: skillKeys.stats(query),
    queryFn: () => api.get<{ rows: StatsRow[]; total: number }>(`/api/skills/stats?${query}`),
  })
}

export function useSkillStatsDaily(query: string, enabled: boolean) {
  return useQuery({
    queryKey: skillKeys.daily(query),
    queryFn: () =>
      api.get<{ day: string; loads: Record<string, number> }[]>(`/api/skills/stats/daily?${query}`),
    enabled,
  })
}

export function useSkillStatsRuns(query: string | null) {
  return useQuery({
    queryKey: skillKeys.statsRuns(query ?? ''),
    queryFn: () => api.get<StatsRun[]>(`/api/skills/stats/runs?${query}`),
    enabled: query !== null,
  })
}

export async function statsCsvUrl(query: string): Promise<string> {
  return `${await getApiBaseUrl()}/api/skills/stats.csv?${query}`
}
