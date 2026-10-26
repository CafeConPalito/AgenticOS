import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CliId, PermissionMode, Tool } from './types'
import { agentKeys } from './agents'
import { inboxKeys } from './inbox'

// Mirrors backend/src/agentic_os/schemas/architect.py (phase 19).

export type ArchitectMode = 'agent' | 'improve_agent' | 'team' | 'improve_team' | 'improve_pipeline'
export type ConversationStatus = 'open' | 'proposed' | 'applied' | 'discarded'
/** Of the conversation's CLI: starting, thinking (a turn runs), idle, asleep (closed). */
export type ArchitectState = 'starting' | 'thinking' | 'idle' | 'asleep'

export interface ArchitectMessage {
  id: string
  role: 'user' | 'architect' | 'system'
  text: string
  /** `{fields}`: what the turn changed; `{unlock_request}`: a field the Architect asks for. */
  tool_events: { fields?: string[]; unlock_request?: string }[]
  created_at: string
}

export interface SheetSkill {
  skill_id: string
  name: string
  mode: 'auto' | 'always' | 'never'
}

export interface SheetAgent {
  id?: string
  name?: string
  role?: string
  description?: string
  color?: string
  team?: string | null
  cli?: CliId
  account?: string | null
  model?: string
  permission_mode?: PermissionMode
  allowed_tools?: Tool[]
  max_concurrency?: number
  can_spawn_subagents?: boolean
  can_create_tasks?: boolean
  can_propose_agents?: boolean
  instructions?: string
  skills?: SheetSkill[]
  new_skills?: { name: string; description: string; body: string }[]
  knowledge?: { doc_id: string; title: string }[]
  connections?: { connection_id: string; name: string }[]
  template?: string | null
}

export interface Sheet {
  agents: Record<string, SheetAgent>
  existing_agents: string[]
  team: { team_id?: string; name?: string; description?: string }
  pipeline: Record<string, unknown> | null
  suggested_connections: {
    registry_ref: string
    source: string
    ref: string
    reason: string
    agent_ref: string
  }[]
  base: Record<string, unknown> | null
}

export interface SheetIssue {
  field: string
  code: string
  message: string
  level: 'error' | 'warning'
}

export interface SheetState {
  sheet: Sheet
  issues: SheetIssue[]
  progress: Record<string, number>
  ready: boolean
  locked: string[]
  refused?: Record<string, string>
}

export interface ConversationSummary {
  id: string
  mode: ArchitectMode
  title: string
  status: ConversationStatus
  state: ArchitectState
  agent_id: string | null
  team_id: string | null
  project_id: string | null
  proposal_id: string | null
  updated_at: string
}

export interface Conversation extends ConversationSummary {
  cli: string | null
  model: string
  run_id: string | null
  messages: ArchitectMessage[]
  sheet: SheetState
}

export interface FieldChange {
  field: string
  before: unknown
  after: unknown
  current: unknown
  conflict: boolean
  diff: string
}

export interface Proposal {
  id: string
  kind: 'new_agent' | 'agent_changes' | 'team' | 'team_changes' | 'pipeline_changes'
  origin: 'architect' | 'agent'
  status: 'pending' | 'applied' | 'partial' | 'rejected'
  reason: string
  conversation_id: string | null
  source_agent_id: string | null
  source_run_id: string | null
  source_task_id: string | null
  target_agent_id: string | null
  target_team_id: string | null
  target_project_id: string | null
  sheet: Sheet | null
  changes: FieldChange[]
  new_skills: { id: string; name: string; description: string }[]
  applied_fields: string[]
  created_at: string
  decided_at: string | null
}

export interface ArchitectSettings {
  cli: '' | 'claude' | 'agy'
  account_id: string
  model: string
  instructions: string
  default_instructions: string
  idle_minutes: number
  max_live: number
}

export const architectKeys = {
  all: ['architect'] as const,
  list: ['architect', 'conversations'] as const,
  detail: (id: string) => ['architect', 'conversations', id] as const,
  settings: ['architect', 'settings'] as const,
  proposal: (id: string) => ['proposals', id] as const,
}

export function useConversations() {
  return useQuery({
    queryKey: architectKeys.list,
    queryFn: () => api.get<ConversationSummary[]>('/api/architect/conversations'),
  })
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: architectKeys.detail(id ?? ''),
    queryFn: () => api.get<Conversation>(`/api/architect/conversations/${id}`),
    enabled: !!id,
  })
}

export interface ConversationCreate {
  mode?: ArchitectMode
  agent_id?: string
  team_id?: string
  project_id?: string
}

export function useCreateConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ConversationCreate) =>
      api.post<Conversation>('/api/architect/conversations', body),
    onSuccess: (created) => {
      queryClient.setQueryData(architectKeys.detail(created.id), created)
      return queryClient.invalidateQueries({ queryKey: architectKeys.list })
    },
  })
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/architect/conversations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: architectKeys.list }),
  })
}

/** Actions on one conversation; each refreshes it. */
export function useConversationActions(id: string) {
  const queryClient = useQueryClient()
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: architectKeys.detail(id) }),
      queryClient.invalidateQueries({ queryKey: architectKeys.list }),
    ])
  const base = `/api/architect/conversations/${id}`
  return {
    send: useMutation({
      mutationFn: (text: string) => api.post<ArchitectMessage>(`${base}/messages`, { text }),
      onSuccess: refresh,
    }),
    interrupt: useMutation({
      mutationFn: () => api.post<{ interrupted: boolean }>(`${base}/interrupt`, {}),
    }),
    reset: useMutation({
      mutationFn: (clearSheet: boolean) =>
        api.post<Conversation>(`${base}/reset`, { clear_sheet: clearSheet }),
      onSuccess: refresh,
    }),
    patchSheet: useMutation({
      mutationFn: (body: { patch: Partial<SheetAgent>; agent_ref?: string }) =>
        api.patch<SheetState>(`${base}/sheet`, body),
      onSuccess: refresh,
    }),
    unlock: useMutation({
      mutationFn: (fields: string[]) => api.post<SheetState>(`${base}/unlock`, { fields }),
      onSuccess: refresh,
    }),
    propose: useMutation({
      mutationFn: () => api.post<Proposal>(`${base}/propose`, {}),
      onSuccess: () =>
        Promise.all([
          refresh(),
          queryClient.invalidateQueries({ queryKey: agentKeys.all }),
          queryClient.invalidateQueries({ queryKey: inboxKeys.all }),
        ]),
    }),
  }
}

export function useProposal(id: string | null | undefined) {
  return useQuery({
    queryKey: architectKeys.proposal(id ?? ''),
    queryFn: () => api.get<Proposal>(`/api/proposals/${id}`),
    enabled: !!id,
  })
}

function useRefreshProposal() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['proposals'] }),
      queryClient.invalidateQueries({ queryKey: agentKeys.all }),
      queryClient.invalidateQueries({ queryKey: inboxKeys.all }),
      queryClient.invalidateQueries({ queryKey: architectKeys.all }),
    ])
}

export interface ApproveBody {
  fields?: string[]
  choices?: Record<string, 'proposed' | 'current'>
  skip_skills?: string[]
}

export function useApproveProposal() {
  const refresh = useRefreshProposal()
  return useMutation({
    mutationFn: ({ id, ...body }: ApproveBody & { id: string }) =>
      api.post<{ proposal: Proposal; notes: string[] }>(`/api/proposals/${id}/approve`, body),
    onSuccess: refresh,
  })
}

export function useRejectProposal() {
  const refresh = useRefreshProposal()
  return useMutation({
    mutationFn: ({ id, archive }: { id: string; archive: boolean }) =>
      api.post<Proposal>(`/api/proposals/${id}/reject`, { archive }),
    onSuccess: refresh,
  })
}

export function useArchitectSettings() {
  return useQuery({
    queryKey: architectKeys.settings,
    queryFn: () => api.get<ArchitectSettings>('/api/settings/architect'),
  })
}

export function useSaveArchitectSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Omit<ArchitectSettings, 'default_instructions'>>) =>
      api.put<ArchitectSettings>('/api/settings/architect', body),
    onSuccess: (saved) => queryClient.setQueryData(architectKeys.settings, saved),
  })
}

/** Live events of one conversation (`/api/architect/conversations/<id>/events`). */
export type ArchitectEvent =
  | { type: 'message'; conversation_id: string; message: ArchitectMessage }
  | { type: 'block'; conversation_id: string; text: string }
  | ({ type: 'sheet'; conversation_id: string } & SheetState)
  | { type: 'state'; conversation_id: string; state: ArchitectState }

/** An event into the cache of its conversation; the blocks of the reply in progress apart. */
export function applyArchitectEvent(
  queryClient: QueryClient,
  conversationId: string,
  event: ArchitectEvent,
  setBlocks: (update: (current: string[]) => string[]) => void,
) {
  if (event.type === 'block') {
    setBlocks((current) => [...current, event.text])
    return
  }
  queryClient.setQueryData<Conversation>(architectKeys.detail(conversationId), (current) => {
    if (!current) return current
    if (event.type === 'message') {
      if (current.messages.some((m) => m.id === event.message.id)) return current
      return { ...current, messages: [...current.messages, event.message] }
    }
    if (event.type === 'sheet') {
      const sheet: SheetState = {
        sheet: event.sheet,
        issues: event.issues,
        progress: event.progress,
        ready: event.ready,
        locked: event.locked,
      }
      return { ...current, sheet }
    }
    return { ...current, state: event.state }
  })
  if (event.type === 'message' && event.message.role === 'architect') setBlocks(() => [])
  if (event.type === 'state' && event.state !== 'thinking') setBlocks(() => [])
}

/** The pending proposals about an agent (its editor shows the changes to review). */
export function usePendingProposals(agentId: string | undefined) {
  return useQuery({
    queryKey: ['proposals', 'agent', agentId ?? ''],
    queryFn: () => api.get<Proposal[]>(`/api/proposals?target_agent_id=${agentId}&status=pending`),
    enabled: !!agentId,
  })
}

export interface AgentChange {
  id: string
  source: 'user' | 'architect' | 'agent' | 'import'
  proposal_id: string | null
  conversation_id: string | null
  /** A proposal: {field: {before, after} | {diff}}; a hand edit: {fields: [...]}. */
  fields: Record<string, unknown>
  created_at: string
}

export function useConfigHistory(agentId: string) {
  return useQuery({
    queryKey: ['agents', agentId, 'config-history'],
    queryFn: () => api.get<AgentChange[]>(`/api/agents/${agentId}/config-history`),
  })
}
