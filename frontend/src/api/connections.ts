import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '@/lib/api'
import type { KnowledgeLevel, KnowledgeScope } from '@/api/knowledge'

/** Phase 18: the catalog of external MCP servers, who gets them, the login of the remote ones,
 * what the runs did with them and the public registries. A secret value never comes back from
 * the backend: only whether it is set. */

export type Transport = 'stdio' | 'http' | 'sse'
export type ConnectionAuth = 'none' | 'oauth'
export type ConnectionOrigin = 'user' | 'template' | 'import' | 'registry'
export type OAuthStatus = 'connected' | 'needs_reauth' | 'disconnected'
export type RunConnectionStatus = 'sent' | 'connected' | 'failed' | 'skipped'

export interface McpTool {
  name: string
  description: string
  read_only: boolean | null
  destructive: boolean | null
  input_schema: Record<string, unknown>
}

export interface ConnectionSecret {
  key: string
  set: boolean
}

export interface ConnectionAssignment {
  id: string
  scope: KnowledgeScope
  project_id: string | null
  agent_id: string | null
}

export interface ConnectionUsage {
  received_runs: number
  used_runs: number
  calls: number
  failed_calls: number
  last_used: string | null
}

export interface ConnectionOAuth {
  status: OAuthStatus
  account_label: string
  expires_at: string | null
  client_pasted: boolean
  redirect_uri: string
}

export interface ConnectionRegistry {
  source: string
  ref: string
  package_type: string
  package: string
  version: string
  repo_url: string
  license: string
  official: boolean
  latest_version: string
  update_available: boolean
}

export interface TestError {
  code: string
  message: string
  detail: string
}

export interface Connection {
  id: string
  name: string
  description: string
  icon: string
  transport: Transport
  command: string
  args: string[]
  cwd: string
  url: string
  env: Record<string, string>
  headers: Record<string, string>
  secrets: ConnectionSecret[]
  auth: ConnectionAuth
  enabled: boolean
  tools: McpTool[]
  resources: { name: string; uri: string; description: string }[]
  prompts: { name: string; description: string }[]
  tested_at: string | null
  test_error: TestError | null
  tools_changed: boolean
  tool_mode: 'all' | 'selected'
  allowed_tools: string[]
  preapproved_tools: string[]
  origin: ConnectionOrigin
  revision: number
  assignments: ConnectionAssignment[]
  usage: ConnectionUsage
  oauth: ConnectionOAuth | null
  registry: ConnectionRegistry | null
  created_at: string
  updated_at: string
}

export interface TemplateField {
  key: string
  label: string
  secret: boolean
  required: boolean
  kind: 'text' | 'path' | 'secret'
  help: string
  help_url: string
}

export interface ConnectionTemplate {
  id: string
  name: string
  description: string
  transport: Transport
  auth: ConnectionAuth
  icon: string
  requires: string[]
  official: boolean
  docs_url: string
  command: string
  url: string
  fields: TemplateField[]
}

export interface ParsedServer {
  name: string
  transport: Transport
  command: string
  args: string[]
  cwd: string
  url: string
  env: Record<string, string>
  headers: Record<string, string>
  secret_keys: string[]
  ignored: string[]
}

export interface FoundConnection {
  id: string
  source: 'claude' | 'claude-project' | 'mcp-json' | 'agy'
  origin: string
  name: string
  transport: Transport
  target: string
  env_keys: string[]
  header_keys: string[]
  has_secrets: boolean
  ignored: string[]
  imported: boolean
}

export interface ProbeError {
  code: string
  message: string
  detail: string
}

export interface ProbeResult {
  ok: boolean
  seconds: number
  server: { name?: string; version?: string }
  tools: McpTool[]
  resources: { name: string; uri: string; description: string }[]
  prompts: { name: string; description: string }[]
  error: ProbeError | null
}

export interface ConnectionTest {
  id: string
  connection_id: string
  state: 'running' | 'done' | 'cancelled'
  seconds: number
  result: ProbeResult | null
  connection: Connection | null
}

export interface OAuthFlow {
  id: string
  connection_id: string
  state: 'starting' | 'waiting' | 'done' | 'failed' | 'cancelled'
  authorization_url: string
  redirect_uri: string
  error: string
  connection: Connection | null
}

export interface ConnectionBrief {
  id: string
  name: string
  description: string
  icon: string
  transport: Transport
  auth: ConnectionAuth
  enabled: boolean
}

export interface EffectiveConnection {
  connection: ConnectionBrief
  level: KnowledgeScope
  tools: number
  tokens: number
}

export interface ExcludedConnection {
  connection: ConnectionBrief
  level: KnowledgeScope
  reason: 'disabled' | 'agent' | 'stage'
}

export interface ConnectionsPreview {
  effective: EffectiveConnection[]
  excluded: ExcludedConnection[]
  total_tools: number
  total_tokens: number
}

export interface AgentConnections extends ConnectionsPreview {
  excluded_ids: string[]
  available: ConnectionBrief[]
}

export interface StageConnections extends ConnectionsPreview {
  excluded_ids: string[]
  agent_id: string | null
}

export interface RunConnection {
  name: string
  connection_id: string | null
  status: RunConnectionStatus
  detail: string
  level: string
  revision: number
  calls: number
  failed_calls: number
  last_call_at: string | null
}

export interface RunToolCall {
  id: string
  connection: string
  tool: string
  started_at: string
  duration_ms: number | null
  ok: boolean | null
  error: string
}

export interface RunConnections {
  connections: RunConnection[]
  calls: RunToolCall[]
}

export interface ConnectionSettings {
  probe_timeout: number
  startup_timeout: number
  agy_grace: number
  oauth_port: number
  registries: Record<string, boolean>
}

export interface Requirement {
  program: string
  found: boolean
  path: string
}

// ---- the public registries
export interface RegistrySource {
  id: string
  title: string
  enabled: boolean
  switchable: boolean
  has_popular: boolean
}

export interface ServerCard {
  source: string
  ref: string
  name: string
  description: string
  author: string
  uses: number | null
  stars: number | null
  updated_at: string | null
  category: string
  url: string
  transport: '' | 'stdio' | 'http' | 'both'
  verified: boolean
  version: string
  installed_connection_id: string | null
}

export interface ServerListing {
  cards: ServerCard[]
  errors: Record<string, string>
}

export interface ServerField {
  key: string
  label: string
  where: 'env' | 'header' | 'arg' | 'url'
  name: string
  secret: boolean
  required: boolean
  default: string
  description: string
}

export interface ServerOption {
  index: number
  kind: 'npm' | 'pypi' | 'oci' | 'remote' | 'command'
  label: string
  package: string
  version: string
  transport: Transport
  url: string
  oauth: boolean
  command: string
  fields: ServerField[]
  requires: string[]
  missing: string[]
}

export interface ServerDetail {
  card: ServerCard
  options: ServerOption[]
  license: string
  repo_url: string
  website: string
  tools: McpTool[]
  security: Record<string, unknown>
  note: string
  installed_as: string | null
}

export interface ServerUpdate {
  connection_id: string
  name: string
  version: string
  latest: string
}

export interface UpdatePreview {
  from: string
  to: string
  changes: { field: string; label: string; from: unknown; to: unknown }[]
}

export const connectionKeys = {
  all: ['connections'] as const,
  list: ['connections', 'list'] as const,
  templates: ['connections', 'templates'] as const,
  requirements: ['connections', 'requirements'] as const,
  scan: ['connections', 'scan'] as const,
  test: (id: string) => ['connections', 'test', id] as const,
  flow: (id: string) => ['connections', 'flow', id] as const,
  agent: (id: string, project: string | null) => ['connections', 'agent', id, project] as const,
  stage: (id: string) => ['connections', 'stage', id] as const,
  run: (id: string) => ['connections', 'run', id] as const,
  settings: ['connections', 'settings'] as const,
  sources: ['connections', 'sources'] as const,
  search: (q: string, source: string | null, transport: string | null) =>
    ['connections', 'search', q, source, transport] as const,
  detail: (source: string, ref: string) => ['connections', 'detail', source, ref] as const,
  update: (id: string) => ['connections', 'update', id] as const,
}

const levelOf = (level: KnowledgeLevel) => ({
  scope: level.scope,
  project_id: level.projectId ?? null,
  agent_id: level.agentId ?? null,
})

function useInvalidateConnections() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: connectionKeys.all })
}

// ------------------------------------------------------------------- the catalog
export function useConnections() {
  return useQuery({
    queryKey: connectionKeys.list,
    queryFn: () => api.get<Connection[]>('/api/connections'),
  })
}

export interface ConnectionInput {
  name: string
  description?: string
  transport: Transport
  command?: string
  args?: string[]
  cwd?: string
  url?: string
  env?: Record<string, string>
  headers?: Record<string, string>
  auth?: ConnectionAuth
  secrets?: Record<string, string>
  level?: KnowledgeLevel
}

/** One connection from the form, or the ones in a pasted `mcpServers` block. */
export function useCreateConnections() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: ({
      jsonText,
      name,
      level,
      ...form
    }: Partial<ConnectionInput> & { jsonText?: string }) =>
      api.post<Connection[]>('/api/connections', {
        ...(jsonText !== undefined ? { json_text: jsonText, name: name ?? '' } : { name, ...form }),
        level: level ? levelOf(level) : undefined,
      }),
    onSuccess: invalidate,
  })
}

export interface ConnectionPatch {
  name?: string
  description?: string
  transport?: Transport
  command?: string
  args?: string[]
  cwd?: string
  url?: string
  env?: Record<string, string>
  headers?: Record<string, string>
  auth?: ConnectionAuth
  enabled?: boolean
  tool_mode?: 'all' | 'selected'
  allowed_tools?: string[]
  preapproved_tools?: string[]
  tools_changed?: boolean
  secrets?: Record<string, string>
  remove_secrets?: string[]
}

export function useUpdateConnection() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: string } & ConnectionPatch) =>
      api.patch<Connection>(`/api/connections/${id}`, patch),
    onSuccess: invalidate,
  })
}

export function useDeleteConnection() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/connections/${id}`),
    onSuccess: invalidate,
  })
}

export function useSetSecret() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: ({ id, key, value }: { id: string; key: string; value: string }) =>
      api.put<Connection>(`/api/connections/${id}/secrets/${encodeURIComponent(key)}`, { value }),
    onSuccess: invalidate,
  })
}

export function useClearSecret() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: ({ id, key }: { id: string; key: string }) =>
      api.delete(`/api/connections/${id}/secrets/${encodeURIComponent(key)}`),
    onSuccess: invalidate,
  })
}

export function useTemplates() {
  return useQuery({
    queryKey: connectionKeys.templates,
    queryFn: () => api.get<ConnectionTemplate[]>('/api/connections/templates'),
    staleTime: Infinity,
  })
}

export function useFromTemplate() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (input: {
      template: string
      name?: string
      values: Record<string, string>
      level?: KnowledgeLevel
    }) =>
      api.post<Connection>('/api/connections/from-template', {
        ...input,
        level: input.level ? levelOf(input.level) : undefined,
      }),
    onSuccess: invalidate,
  })
}

export function useParseJson() {
  return useMutation({
    mutationFn: (input: { text: string; name?: string }) =>
      api.post<{ servers: ParsedServer[] }>('/api/connections/parse', input),
  })
}

export function useRequirements() {
  return useQuery({
    queryKey: connectionKeys.requirements,
    queryFn: () => api.get<Requirement[]>('/api/connections/requirements'),
  })
}

export async function fetchExport(id: string): Promise<string> {
  const data = await api.get<unknown>(`/api/connections/${id}/export`)
  return JSON.stringify(data, null, 2)
}

// ------------------------------------------------------------------- import
export function useScanConnections(enabled: boolean) {
  return useQuery({
    queryKey: connectionKeys.scan,
    queryFn: () => api.get<FoundConnection[]>('/api/connections/import/scan'),
    enabled,
  })
}

export interface ImportChoice {
  id: string
  name?: string
  level: KnowledgeLevel
}

export function useImportConnections() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (items: ImportChoice[]) =>
      api.post<{
        created: Connection[]
        problems: { id: string | null; name: string; reason: string }[]
      }>('/api/connections/import', {
        items: items.map(({ level, ...rest }) => ({ ...rest, ...levelOf(level) })),
      }),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- tests of a connection
export function useStartTest() {
  return useMutation({
    mutationFn: (id: string) => api.post<ConnectionTest>(`/api/connections/${id}/test`),
  })
}

/** Follows a test every second until it is done; the catalog is refreshed once it ends. */
export function useTest(testId: string | null) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: connectionKeys.test(testId ?? ''),
    queryFn: () => api.get<ConnectionTest>(`/api/connections/tests/${testId}`),
    enabled: testId !== null,
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 1000 : false),
  })
  const state = query.data?.state
  useEffect(() => {
    // Only the list: invalidating the test's own key from inside its fetch would restart it.
    if (state && state !== 'running') {
      void queryClient.invalidateQueries({ queryKey: connectionKeys.list })
    }
  }, [state, queryClient])
  return query
}

export function cancelTest(testId: string) {
  return api.delete(`/api/connections/tests/${testId}`)
}

// ------------------------------------------------------------------- the login of a remote one
export function useStartOAuth() {
  return useMutation({
    mutationFn: ({
      id,
      clientId,
      clientSecret,
    }: {
      id: string
      clientId?: string
      clientSecret?: string
    }) =>
      api.post<OAuthFlow>(`/api/connections/${id}/oauth/start`, {
        client_id: clientId ?? '',
        client_secret: clientSecret ?? '',
      }),
  })
}

export function useOAuthFlow(flowId: string | null) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: connectionKeys.flow(flowId ?? ''),
    queryFn: () => api.get<OAuthFlow>(`/api/connections/oauth/flows/${flowId}`),
    enabled: flowId !== null,
    refetchInterval: (q) =>
      ['starting', 'waiting'].includes(q.state.data?.state ?? '') ? 1000 : false,
  })
  const state = query.data?.state
  useEffect(() => {
    if (state === 'done') void queryClient.invalidateQueries({ queryKey: connectionKeys.list })
  }, [state, queryClient])
  return query
}

/** The backend opens the login page in the system's browser (the UI has no shell). */
export function openOAuthPage(flowId: string) {
  return api.post<void>(`/api/connections/oauth/flows/${flowId}/open`)
}

export function cancelOAuthFlow(flowId: string) {
  return api.delete(`/api/connections/oauth/flows/${flowId}`)
}

export function useDisconnectOAuth() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (id: string) => api.post<Connection>(`/api/connections/${id}/oauth/disconnect`),
    onSuccess: invalidate,
  })
}

export function useRefreshOAuth() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (id: string) => api.post<Connection>(`/api/connections/${id}/oauth/refresh`),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- who gets what
export function useAddAssignment() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: ({ id, level }: { id: string; level: KnowledgeLevel }) =>
      api.post<Connection>(`/api/connections/${id}/assignments`, levelOf(level)),
    onSuccess: invalidate,
  })
}

export function useRemoveAssignment() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: ({ id, assignmentId }: { id: string; assignmentId: string }) =>
      api.delete(`/api/connections/${id}/assignments/${assignmentId}`),
    onSuccess: invalidate,
  })
}

export function useAgentConnections(agentId: string, projectId: string | null = null) {
  return useQuery({
    queryKey: connectionKeys.agent(agentId, projectId),
    queryFn: () =>
      api.get<AgentConnections>(
        `/api/agents/${agentId}/connections${projectId ? `?project_id=${projectId}` : ''}`,
      ),
  })
}

export function usePutAgentExclusions(agentId: string) {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (excluded: string[]) =>
      api.put<AgentConnections>(`/api/agents/${agentId}/connections`, { excluded }),
    onSuccess: invalidate,
  })
}

export function useStageConnections(stageId: string) {
  return useQuery({
    queryKey: connectionKeys.stage(stageId),
    queryFn: () => api.get<StageConnections>(`/api/stages/${stageId}/connections`),
  })
}

export function usePutStageExclusions(stageId: string) {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (excluded: string[]) =>
      api.put<StageConnections>(`/api/stages/${stageId}/connections`, { excluded }),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- what a run did
export function useRunConnections(runId: string) {
  return useQuery({
    queryKey: connectionKeys.run(runId),
    queryFn: () => api.get<RunConnections>(`/api/runs/${runId}/connections`),
    refetchInterval: 5000,
  })
}

// ------------------------------------------------------------------- settings
export function useConnectionSettings() {
  return useQuery({
    queryKey: connectionKeys.settings,
    queryFn: () => api.get<ConnectionSettings>('/api/settings/connections'),
  })
}

export function useSaveConnectionSettings() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (values: Partial<ConnectionSettings>) =>
      api.put<ConnectionSettings>('/api/settings/connections', values),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- the public registries
export function useRegistrySources() {
  return useQuery({
    queryKey: connectionKeys.sources,
    queryFn: () => api.get<RegistrySource[]>('/api/connections/registries'),
  })
}

export function useServerSearch(query: string, source: string | null, transport: string | null) {
  const params = new URLSearchParams()
  if (query) params.set('query', query)
  if (source) params.set('source', source)
  if (transport) params.set('transport', transport)
  return useQuery({
    queryKey: connectionKeys.search(query, source, transport),
    queryFn: () => api.get<ServerListing>(`/api/connections/registries/search?${params}`),
  })
}

export function useServerDetail(source: string | null, ref: string | null) {
  return useQuery({
    queryKey: connectionKeys.detail(source ?? '', ref ?? ''),
    queryFn: () =>
      api.get<ServerDetail>(
        `/api/connections/registries/detail?${new URLSearchParams({ source: source!, ref: ref! })}`,
      ),
    enabled: source !== null && ref !== null,
    retry: false,
  })
}

export function useInstallServer() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (input: {
      source: string
      ref: string
      option: number
      name?: string
      values: Record<string, string>
      oauth?: boolean
      level?: KnowledgeLevel
    }) =>
      api.post<Connection>('/api/connections/registries/install', {
        ...input,
        level: input.level ? levelOf(input.level) : undefined,
      }),
    onSuccess: invalidate,
  })
}

export function useCheckUpdates() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: () => api.post<ServerUpdate[]>('/api/connections/updates/check'),
    onSuccess: invalidate,
  })
}

export function useUpdatePreview(id: string | null) {
  return useQuery({
    queryKey: connectionKeys.update(id ?? ''),
    queryFn: () => api.get<UpdatePreview>(`/api/connections/${id}/update`),
    enabled: id !== null,
    retry: false,
  })
}

export function useApplyUpdate() {
  const invalidate = useInvalidateConnections()
  return useMutation({
    mutationFn: (id: string) => api.post<Connection>(`/api/connections/${id}/update`),
    onSuccess: invalidate,
  })
}
