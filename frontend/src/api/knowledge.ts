import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, getApiBaseUrl } from '@/lib/api'

export type KnowledgeScope = 'general' | 'project' | 'agent'
export type KnowledgeMode = 'auto' | 'context' | 'search' | 'off'
export type DocStatus =
  'queued' | 'converting' | 'images' | 'describing' | 'indexing' | 'ready' | 'failed'
export type Presence = 'ok' | 'missing' | 'changed'
export type SourceKind = 'file' | 'image' | 'url'
export type Viewer = 'pdf' | 'image' | 'markdown' | 'text' | 'code' | 'csv' | 'url' | 'system'

export interface KnowledgeDoc {
  id: string
  scope: KnowledgeScope
  project_id: string | null
  agent_id: string | null
  title: string
  description: string
  mode: KnowledgeMode
  describe_images: boolean | null
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
  found_by: 'meaning' | 'words' | 'both'
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
    default:
      break
  }
}
