import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export type ModelKind = 'embedding' | 'ocr' | 'vision' | 'speech' | 'engine'
export type ModelState = 'absent' | 'partial' | 'downloading' | 'ready' | 'error'

export interface LocalModel {
  id: string
  kind: ModelKind
  title: string
  license: string
  size: number
  default: boolean
  selected: boolean
  needs_account: boolean
  available: boolean
  bundled: boolean
  state: ModelState
  done: number
  total: number
  error_code: string | null
  error_message: string | null
}

export interface LocalModels {
  models: LocalModel[]
  disk: { models: number; engines: number; free: number }
}

export interface ModelSelection {
  embedding: string | null
  ocr: string | null
  vision: string | null
  speech: string | null
  reindex?: boolean
}

export interface HfToken {
  configured: boolean
  source: 'env' | 'file' | 'git' | null
}

export const localModelKeys = {
  all: ['local-models'] as const,
  selection: ['local-models', 'selection'] as const,
  token: ['local-models', 'token'] as const,
}

/** The catalogue with the state of each model; while something downloads it is read each second. */
export function useLocalModels() {
  return useQuery({
    queryKey: localModelKeys.all,
    queryFn: () => api.get<LocalModels>('/api/local-models'),
    refetchInterval: (query) =>
      query.state.data?.models.some((m) => m.state === 'downloading') ? 1000 : false,
  })
}

function useRefresh() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: localModelKeys.all })
}

export function useDownloadModel() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => api.post<LocalModel>(`/api/local-models/${id}/download`),
    onSuccess: refresh,
  })
}

export function useCancelModel() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => api.post<LocalModel>(`/api/local-models/${id}/cancel`),
    onSuccess: refresh,
  })
}

export function useDeleteModel() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/local-models/${id}`),
    onSuccess: refresh,
  })
}

export function useModelSelection() {
  return useQuery({
    queryKey: localModelKeys.selection,
    queryFn: () => api.get<ModelSelection>('/api/settings/local-models'),
  })
}

export function useSelectModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (
      choice: Partial<Pick<ModelSelection, 'embedding' | 'ocr' | 'vision' | 'speech'>>,
    ) => api.put<ModelSelection>('/api/settings/local-models', choice),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: localModelKeys.all }),
  })
}

export function useHfToken() {
  return useQuery({
    queryKey: localModelKeys.token,
    queryFn: () => api.get<HfToken>('/api/settings/huggingface-token'),
  })
}

export function useSaveHfToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string | null) =>
      api.put<HfToken>('/api/settings/huggingface-token', { token }),
    onSuccess: (token) => queryClient.setQueryData(localModelKeys.token, token),
  })
}
