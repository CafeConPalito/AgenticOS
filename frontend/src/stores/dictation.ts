import { create } from 'zustand'

/** What the person sees of a dictation, per field. The work itself is in
 * `lib/dictation/controller.ts`. */
export interface Recording {
  fieldId: string
  startedAt: number
  /** 0..1, for the meter. */
  level: number
  mode: 'click' | 'hold'
  /** The limit is near (it will be cut shortly). */
  nearLimit: boolean
}

export interface Job {
  id: number
  fieldId: string
  status: 'queued' | 'transcribing'
}

export interface DictationError {
  /** `permission`, `no_device`, `no_model`, `no_speech`… (i18n key under `dictation.errors`). */
  code: string
  message?: string
}

export type FieldPhase = 'idle' | 'recording' | 'queued' | 'transcribing' | 'error'

interface DictationState {
  recording: Recording | null
  jobs: Job[]
  errors: Record<string, DictationError>
  /** The dialog that offers to download a speech model. */
  downloadOpen: boolean
  setDownloadOpen: (open: boolean) => void
}

export const useDictation = create<DictationState>()((set) => ({
  recording: null,
  jobs: [],
  errors: {},
  downloadOpen: false,
  setDownloadOpen: (downloadOpen) => set({ downloadOpen }),
}))

/** The phase of one field. */
export function phaseOf(state: DictationState, fieldId: string): FieldPhase {
  if (state.recording?.fieldId === fieldId) return 'recording'
  const job = state.jobs.find((j) => j.fieldId === fieldId)
  if (job) return job.status === 'transcribing' ? 'transcribing' : 'queued'
  return state.errors[fieldId] ? 'error' : 'idle'
}
