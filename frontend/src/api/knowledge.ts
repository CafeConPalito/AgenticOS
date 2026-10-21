import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, getApiBaseUrl } from '@/lib/api'

export type KnowledgeScope = 'general' | 'project' | 'agent'
export type KnowledgeMode = 'auto' | 'context' | 'search' | 'off'
export type DocStatus =
  'queued' | 'converting' | 'images' | 'describing' | 'indexing' | 'ready' | 'failed'
export type Presence = 'ok' | 'missing' | 'changed'
export type SourceKind = 'file' | 'image' | 'url' | 'markdown'
export type Viewer =
  'pdf' | 'image' | 'markdown' | 'text' | 'code' | 'csv' | 'url' | 'system' | 'none'
/** Who brought a document: the person, or an agent (its proposal was accepted). */
export type Origin = 'user' | 'agent'
/** `proposed`: an agent's proposal waiting for the person; nobody reads it until accepted. */
export type Review = 'none' | 'proposed'

/** Who proposed an agent's document, when and from which run. */
export interface Provenance {
  agent_id: string | null
  agent_name: string
  run_id: string | null
  task_id: string | null
  task_title: string
  proposed_at: string
  suggested_scope: '' | KnowledgeScope
  replaces_id: string | null
  decided_at: string | null
  edited: boolean
}

/** «Derived from»: `id` is null when that document was deleted (the title remembers it). */
export interface DocSource {
  id: string | null
  title: string
  removed: boolean
}

export interface KnowledgeDoc {
  id: string
  scope: KnowledgeScope
  project_id: string | null
  agent_id: string | null
  title: string
  description: string
  mode: KnowledgeMode
  describe_images: boolean | null
  origin: Origin
  review: Review
  summary: string
  provenance: Provenance | null
  sources: DocSource[]
  source_kind: SourceKind
  path: string | null
  url: string | null
  file_name: string | null
  extension: string
  viewer: Viewer
  size: number | null
  presence: Presence
  status: DocStatus
  progress_done: number
  progress_total: number
  error_code: string | null
  error_message: string | null
  notice: string | null
  md_tokens: number
  image_count: number
  has_markdown: boolean
  embed_model: string
  processed_at: string | null
  created_at: string
  updated_at: string
}

/** Where a document lives; `scope: general` has no owner. */
export interface KnowledgeLevel {
  scope: KnowledgeScope
  projectId?: string
  agentId?: string
}

export interface AddItem {
  path: string
  doc: KnowledgeDoc | null
  error_code: string | null
  message: string
}

export interface DocImage {
  ord: number
  kind: string
  location: string
  width: number
  height: number
  ocr_text: string
  description: string
  described_by: string
}

export interface SearchHit {
  doc_id: string
  title: string
  scope: KnowledgeScope
  chunk: number
  heading: string
  location: string
  text: string
  score: number
  found_by: 'meaning' | 'words' | 'both' | 'graph'
  /** For «graph»: how it was reached from a better result («deriva de «Manual»»). */
  via: string
  images: number[]
}

export interface SearchResult {
  hits: SearchHit[]
  mode: 'hybrid' | 'words'
  model: string | null
}

export interface QueueState {
  paused: boolean
  queued: number
  active: string[]
  mode: string
  reindexing?: boolean
}

export interface SystemLoad {
  cpu: { percent: number; app_percent: number; cores: number }
  memory: { percent: number; used_mb: number; total_mb: number; app_mb: number }
  gpu: { percent: number; app_percent: number } | null
}

export interface KnowledgeSettings {
  max_file_mb: number
  context_budget: number
  small_doc_tokens: number
  concurrency: number
  threads: number
  describe_images: boolean
  describer: 'cli' | 'local'
  describer_cli: '' | 'claude' | 'agy'
  describer_account: string
  describer_model: string
  proposals_enabled: boolean
  proposals_per_run: number
  proposals_max_tokens: number
  graph_threshold: number
  graph_max_neighbors: number
  graph_expand: number
}

export const knowledgeKeys = {
  docs: ['knowledge', 'docs'] as const,
  level: (level: KnowledgeLevel | 'all') => ['knowledge', 'docs', level] as const,
  doc: (id: string) => ['knowledge', 'doc', id] as const,
  markdown: (id: string) => ['knowledge', 'doc', id, 'markdown'] as const,
  images: (id: string) => ['knowledge', 'doc', id, 'images'] as const,
  queue: ['knowledge', 'queue'] as const,
  system: ['knowledge', 'system'] as const,
  settings: ['knowledge', 'settings'] as const,
  graph: ['knowledge', 'graph'] as const,
}

function levelQuery(level: KnowledgeLevel | 'all'): string {
  if (level === 'all') return ''
  const params = new URLSearchParams({ scope: level.scope })
  if (level.projectId) params.set('project_id', level.projectId)
  if (level.agentId) params.set('agent_id', level.agentId)
  return `?${params}`
}

function levelBody(level: KnowledgeLevel) {
  return {
    scope: level.scope,
    project_id: level.projectId ?? null,
    agent_id: level.agentId ?? null,
  }
}

export function useKnowledgeDocs(level: KnowledgeLevel | 'all') {
  return useQuery({
    queryKey: knowledgeKeys.level(level),
    queryFn: () => api.get<KnowledgeDoc[]>(`/api/knowledge/docs${levelQuery(level)}`),
  })
}

export function useKnowledgeDoc(id: string | null) {
  return useQuery({
    queryKey: knowledgeKeys.doc(id ?? ''),
    queryFn: () => api.get<KnowledgeDoc>(`/api/knowledge/docs/${id}`),
    enabled: id !== null,
  })
}

function useInvalidateDocs() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: knowledgeKeys.docs })
}

export function useAddFiles(level: KnowledgeLevel) {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: (paths: string[]) =>
      api.post<AddItem[]>('/api/knowledge/docs/files', { ...levelBody(level), paths }),
    onSuccess: invalidate,
  })
}

export function useAddUrl(level: KnowledgeLevel) {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: (url: string) =>
      api.post<KnowledgeDoc>('/api/knowledge/docs/url', { ...levelBody(level), url }),
    onSuccess: invalidate,
  })
}

export type DocPatch = Partial<
  Pick<KnowledgeDoc, 'title' | 'description' | 'mode' | 'describe_images'>
>

export function useUpdateDoc() {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: ({ id, ...patch }: DocPatch & { id: string }) =>
      api.patch<KnowledgeDoc>(`/api/knowledge/docs/${id}`, patch),
    onSuccess: invalidate,
  })
}

export function useMoveDoc() {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: ({ id, level }: { id: string; level: KnowledgeLevel }) =>
      api.patch<KnowledgeDoc>(`/api/knowledge/docs/${id}`, levelBody(level)),
    onSuccess: invalidate,
  })
}

export function useDeleteDoc() {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/knowledge/docs/${id}`),
    onSuccess: invalidate,
  })
}

export function useReprocessDoc() {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: (id: string) => api.post<KnowledgeDoc>(`/api/knowledge/docs/${id}/reprocess`),
    onSuccess: invalidate,
  })
}

/** What the person decided about a proposal; everything optional (accept it as it is). */
export interface AcceptInput {
  id: string
  title?: string
  description?: string
  markdown?: string
  scope?: KnowledgeScope
  project_id?: string | null
  agent_id?: string | null
  /** Delete the version it replaces once this one is ready. */
  replace?: boolean
}

export function useAcceptProposal() {
  const invalidate = useInvalidateDocs()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: AcceptInput) =>
      api.post<KnowledgeDoc>(`/api/knowledge/docs/${id}/accept`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['inbox'] })
      return invalidate()
    },
  })
}

export function useRejectProposal() {
  const invalidate = useInvalidateDocs()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      api.post(`/api/knowledge/docs/${id}/reject`, { reason: reason ?? '' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['inbox'] })
      return invalidate()
    },
  })
}

export function useRelocateDoc() {
  const invalidate = useInvalidateDocs()
  return useMutation({
    mutationFn: ({ id, path, confirm }: { id: string; path: string; confirm?: boolean }) =>
      api.post<{ doc: KnowledgeDoc; reprocess: boolean }>(`/api/knowledge/docs/${id}/relocate`, {
        path,
        confirm: confirm ?? false,
      }),
    onSuccess: invalidate,
  })
}

export function useOpenDoc() {
  return useMutation({ mutationFn: (id: string) => api.post(`/api/knowledge/docs/${id}/open`) })
}

export function useRevealDoc() {
  return useMutation({ mutationFn: (id: string) => api.post(`/api/knowledge/docs/${id}/reveal`) })
}

export function useDocMarkdown(id: string, enabled: boolean) {
  return useQuery({
    queryKey: knowledgeKeys.markdown(id),
    queryFn: () =>
      api.get<{ title: string; markdown: string; tokens: number }>(
        `/api/knowledge/docs/${id}/markdown`,
      ),
    enabled,
  })
}

export function useDocImages(id: string, enabled: boolean) {
  return useQuery({
    queryKey: knowledgeKeys.images(id),
    queryFn: () => api.get<DocImage[]>(`/api/knowledge/docs/${id}/images`),
    enabled,
  })
}

/** The text of the original, for the text, code and CSV viewers. */
export function useOriginalText(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['knowledge', 'doc', id, 'original'],
    queryFn: async () => {
      const base = await getApiBaseUrl()
      const response = await fetch(`${base}/api/knowledge/docs/${id}/original`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.text()
    },
    enabled,
  })
}

/** The address the backend serves a document's original (or a picture of it) at. */
export function useApiBase(): string | null {
  const [base, setBase] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    void getApiBaseUrl().then((url) => live && setBase(url))
    return () => {
      live = false
    }
  }, [])
  return base
}

export const originalPath = (id: string) => `/api/knowledge/docs/${id}/original`
export const imagePath = (id: string, ord: number) => `/api/knowledge/docs/${id}/images/${ord}`

export function useSearchKnowledge() {
  return useMutation({
    mutationFn: (input: { query: string; projectId?: string; agentId?: string }) =>
      api.post<SearchResult>('/api/knowledge/search', {
        query: input.query,
        project_id: input.projectId ?? null,
        agent_id: input.agentId ?? null,
      }),
  })
}

export function useQueue() {
  return useQuery({
    queryKey: knowledgeKeys.queue,
    queryFn: () => api.get<QueueState>('/api/knowledge/queue'),
  })
}

export function useSetPaused() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (paused: boolean) =>
      api.post<QueueState>(`/api/knowledge/queue/${paused ? 'pause' : 'resume'}`),
    onSuccess: (state) => queryClient.setQueryData(knowledgeKeys.queue, state),
  })
}

// ------------------------------------------------------------------------------ the graph
/** A document as a node; a «ghost» is a source that was deleted (only its name is left). */
export interface GraphNode {
  id: string
  title: string
  summary: string
  ghost: boolean
  origin: Origin
  source_kind: SourceKind | null
  review: Review
  scope: KnowledgeScope | null
  project_id: string | null
  agent_id: string | null
  mode: KnowledgeMode | null
  status: DocStatus | null
  presence: Presence | null
  md_tokens: number
  topic: number | null
}

export interface GraphEdge {
  kind: 'derived' | 'related'
  /** «derived»: the document it was derived from. */
  source: string
  target: string
  weight: number
}

export interface GraphTopic {
  id: number
  name: string
  size: number
  /** The «Sueltos» group: documents with no link at all. */
  loose: boolean
  central: string[]
  neighbors: number[]
}

export interface KnowledgeGraph {
  version: number
  nodes: GraphNode[]
  edges: GraphEdge[]
  topics: GraphTopic[]
}

/** What part of the library the graph shows: the context of a project or an agent, or all of it. */
export interface GraphScope {
  projectId?: string
  agentId?: string
  everything?: boolean
}

export function useKnowledgeGraph(scope: GraphScope) {
  const params = new URLSearchParams()
  if (scope.everything) params.set('all', 'true')
  else {
    if (scope.projectId) params.set('project_id', scope.projectId)
    if (scope.agentId) params.set('agent_id', scope.agentId)
  }
  const query = params.toString()
  return useQuery({
    queryKey: [...knowledgeKeys.graph, query] as const,
    queryFn: () => api.get<KnowledgeGraph>(`/api/knowledge/graph${query ? `?${query}` : ''}`),
  })
}

/** What «Explorar» reaches from a question or a document: each document and how it was reached. */
export interface ExploredNode {
  id: string
  title: string
  /** 0 for the starting points. */
  depth: number
  /** 1 for a starting point; smaller the longer and weaker the path. */
  strength: number
  /** The titles along the path, from the starting point to this document. */
  path: string[]
  /** How each step was taken: «derivado de», «origen de» or «relacionado 0,52». */
  reasons: string[]
}

export interface ExplorationResult {
  nodes: ExploredNode[]
}

export function useKnowledgeSettings() {
  return useQuery({
    queryKey: knowledgeKeys.settings,
    queryFn: () => api.get<KnowledgeSettings>('/api/settings/knowledge'),
  })
}

export function useSaveKnowledgeSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: Partial<KnowledgeSettings>) =>
      api.put<KnowledgeSettings>('/api/settings/knowledge', patch),
    onSuccess: (settings) => queryClient.setQueryData(knowledgeKeys.settings, settings),
  })
}

export type KnowledgeEvent =
  | { type: 'doc'; doc: KnowledgeDoc }
  | { type: 'doc_removed'; id: string }
  | ({ type: 'queue' } & QueueState)
  | ({ type: 'system' } & SystemLoad)
  | { type: 'reindex'; done: number; total: number; model: string }
  | { type: 'model'; id: string; state: string; done?: number; total?: number }
  | { type: 'graph'; version: number }

/** Does a list (identified by the level in its query key) show this document? */
function belongsTo(level: unknown, doc: KnowledgeDoc): boolean {
  if (level === 'all') return true
  const wanted = level as KnowledgeLevel
  return (
    wanted.scope === doc.scope &&
    (wanted.projectId ?? null) === doc.project_id &&
    (wanted.agentId ?? null) === doc.agent_id
  )
}

/** Applies one live event to the cached lists, so the UI follows the queue without polling. */
export function applyKnowledgeEvent(queryClient: QueryClient, event: KnowledgeEvent) {
  switch (event.type) {
    case 'doc': {
      const doc = event.doc
      queryClient.setQueryData(knowledgeKeys.doc(doc.id), doc)
      queryClient.setQueriesData<KnowledgeDoc[]>({ queryKey: knowledgeKeys.docs }, (list) =>
        list?.map((item) => (item.id === doc.id ? doc : item)),
      )
      // Only the lists of the document's own level can be out of date: one that should have it
      // and does not (added elsewhere), or one that has it and should not (moved to another level).
      // Progress events come several times a second: the other lists must not be read again.
      void queryClient.invalidateQueries({
        queryKey: knowledgeKeys.docs,
        predicate: (query) => {
          const list = query.state.data as KnowledgeDoc[] | undefined
          if (!Array.isArray(list)) return false
          const has = list.some((item) => item.id === doc.id)
          return belongsTo(query.queryKey[2], doc) !== has
        },
      })
      if (doc.status === 'ready' || doc.status === 'failed') {
        void queryClient.invalidateQueries({ queryKey: knowledgeKeys.markdown(doc.id) })
        void queryClient.invalidateQueries({ queryKey: knowledgeKeys.images(doc.id) })
      }
      break
    }
    case 'doc_removed':
      queryClient.setQueriesData<KnowledgeDoc[]>({ queryKey: knowledgeKeys.docs }, (list) =>
        list?.filter((item) => item.id !== event.id),
      )
      void queryClient.invalidateQueries({ queryKey: knowledgeKeys.graph })
      break
    case 'queue': {
      const { type: _type, ...state } = event
      void _type
      queryClient.setQueryData(knowledgeKeys.queue, state)
      break
    }
    case 'system': {
      const { type: _type, ...load } = event
      void _type
      queryClient.setQueryData(knowledgeKeys.system, load)
      break
    }
    case 'model':
      void queryClient.invalidateQueries({ queryKey: ['local-models'] })
      break
    case 'graph':
      void queryClient.invalidateQueries({ queryKey: knowledgeKeys.graph })
      break
    default:
      break
  }
}
