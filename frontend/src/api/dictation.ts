import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiFetch } from '@/lib/api'

export interface DictationSettings {
  enabled: boolean
  /** `auto` or an ISO 639-1 code. */
  language: string
  /** Held to dictate in the focused field, e.g. `Ctrl+Space`. */
  shortcut: string
  max_seconds: number
  vocabulary: string[]
}

export type DictationReason = 'disabled' | 'no_model' | 'engine_missing'

export interface DictationStatus {
  enabled: boolean
  /** A dictation can start now. */
  ready: boolean
  reason: DictationReason | null
  /** The speech model that would be used (chosen or default). */
  model: string | null
  state: 'stopped' | 'ready' | 'busy'
  queued: number
}

export interface Transcript {
  text: string
  seconds: number
  model: string
}

export const dictationKeys = {
  status: ['dictation', 'status'] as const,
  settings: ['settings', 'dictation'] as const,
}

/** Whether the microphones are shown, and whether dictating would work right now. */
export function useDictationStatus() {
  return useQuery({
    queryKey: dictationKeys.status,
    queryFn: () => api.get<DictationStatus>('/api/dictation/status'),
    staleTime: 15_000,
    retry: false,
  })
}

export function useDictationSettings() {
  return useQuery({
    queryKey: dictationKeys.settings,
    queryFn: () => api.get<DictationSettings>('/api/settings/dictation'),
    staleTime: 60_000,
    retry: false,
  })
}

export function useSaveDictationSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: Partial<DictationSettings>) =>
      api.put<DictationSettings>('/api/settings/dictation', values),
    onSuccess: (saved) => {
      queryClient.setQueryData(dictationKeys.settings, saved)
      void queryClient.invalidateQueries({ queryKey: dictationKeys.status })
    },
  })
}

/** Sends the recording (a 16 kHz mono WAV) to be transcribed on this machine. */
/** `partial` (phase 23): the text so far while the person speaks; the backend answers 409
 * `busy` when the engine is at work, and that turn is skipped. */
export function transcribe(wav: Blob, signal?: AbortSignal, partial = false): Promise<Transcript> {
  const query = partial ? '?partial=true' : ''
  return apiFetch<Transcript>(`/api/dictation/transcribe${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'audio/wav' },
    body: wav,
    signal,
  })
}

/** The person started to talk: the backend loads the model while they do. */
export function warmUp(): Promise<void> {
  return apiFetch<void>('/api/dictation/warmup', { method: 'POST' })
}
