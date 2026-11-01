/** Dictation: one recording at a time, transcriptions one after the other, the text inserted at
 * the cursor of the field where the recording began (ADR 0023). Not a React component: the
 * shortcut, the microphone buttons and the tests all drive it. */

import { toast } from 'sonner'
import { transcribe, warmUp } from '@/api/dictation'
import { ApiError } from '@/lib/api'
import i18n from '@/i18n'
import { useDictation, type DictationError } from '@/stores/dictation'
import { insertText, trackAnchor, type Field } from './insert'
import { LiveTranscript, TICK_MS } from './live'
import { MicrophoneError, microphone, type Recorder, type Recording } from './recorder'

/** A hold shorter than this was an accident, not a dictation. */
export const MIN_HOLD_MS = 300
/** The warning comes this long before the limit. */
export const WARNING_SECONDS = 15
/** Errors that mean «download a speech model first». */
const MISSING = new Set(['no_model', 'engine_missing'])

let recorder: Recorder = microphone
const fields = new Map<string, Field>()
let session: Session | null = null
let queue: Job[] = []
let nextJobId = 1
let running = false
let starting = false
let releaseRequested = false

interface Session {
  fieldId: string
  field: Field
  recording: Recording
  tracker: ReturnType<typeof trackAnchor>
  mode: 'click' | 'hold'
  startedAt: number
  timers: ReturnType<typeof setTimeout>[]
  onKey: (event: KeyboardEvent) => void
  /** Phase 23: the text as it is spoken (null when the recorder cannot be read while it goes). */
  live: LiveTranscript | null
  ticker: ReturnType<typeof setInterval> | null
}

interface Job {
  id: number
  fieldId: string
  field: Field
  /** The whole recording, or (`live`) only what was left after the last piece. */
  wav: Blob | null
  live: LiveTranscript | null
  tracker: ReturnType<typeof trackAnchor>
}

/** For the tests: another microphone. */
export function setRecorder(next: Recorder): void {
  recorder = next
}

/** The microphone in use (the settings page tests it). */
export function currentRecorder(): Recorder {
  return recorder
}

export function registerField(id: string, field: Field): () => void {
  fields.set(id, field)
  return () => {
    if (fields.get(id) === field) fields.delete(id)
    // The field is gone while it was being recorded: nobody sees the microphone any more.
    if (session?.fieldId === id) cancelDictation()
  }
}

export function fieldIdOf(element: Element | null): string | null {
  for (const [id, field] of fields) if (field === element) return id
  return null
}

/** For the tests: forget everything. */
export function resetDictation(): void {
  session?.recording.cancel()
  session?.tracker.stop()
  session?.live?.stop()
  if (session?.ticker) clearInterval(session.ticker)
  for (const timer of session?.timers ?? []) clearTimeout(timer)
  if (session) window.removeEventListener('keydown', session.onKey, true)
  for (const job of queue) {
    job.tracker.stop()
    job.live?.stop()
  }
  session = null
  queue = []
  running = false
  starting = false
  releaseRequested = false
  fields.clear()
  useDictation.setState({ recording: null, jobs: [], errors: {}, downloadOpen: false })
}

function setError(fieldId: string, error: DictationError): void {
  useDictation.setState((s) => ({ errors: { ...s.errors, [fieldId]: error } }))
}

export function clearError(fieldId: string): void {
  useDictation.setState((s) => {
    if (!s.errors[fieldId]) return s
    const errors = { ...s.errors }
    delete errors[fieldId]
    return { errors }
  })
}

function reportError(fieldId: string, code: string, message?: string): void {
  setError(fieldId, { code, message })
  if (MISSING.has(code)) {
    useDictation.getState().setDownloadOpen(true)
    return
  }
  const text = i18n.t(`dictation.errors.${code}`, { defaultValue: message ?? code })
  if (code === 'no_speech') toast.info(text)
  else toast.error(text)
}

export interface StartOptions {
  mode: 'click' | 'hold'
  maxSeconds: number
  deviceId?: string
}

/** Starts recording for the field. Another recording in progress is ended first (and its text
 * still arrives where it was started). */
export async function startDictation(fieldId: string, options: StartOptions): Promise<void> {
  const field = fields.get(fieldId)
  if (!field || starting) return
  starting = true
  releaseRequested = false
  try {
    if (session) await stopDictation()
    await begin(fieldId, field, options)
  } finally {
    starting = false
  }
  // The key was let go while the microphone was still opening (the permission prompt).
  if (releaseRequested && session?.mode === 'hold') await stopDictation()
  releaseRequested = false
}

/** The hold shortcut was released. */
export function releaseHold(): void {
  if (starting) releaseRequested = true
  else if (session?.mode === 'hold') void stopDictation()
}

async function begin(fieldId: string, field: Field, options: StartOptions): Promise<void> {
  clearError(fieldId)
  const tracker = trackAnchor(field, {
    start: field.selectionStart ?? field.value.length,
    end: field.selectionEnd ?? field.value.length,
  })
  let recording: Recording
  let live: LiveTranscript | null = null
  try {
    recording = await recorder.start({
      deviceId: options.deviceId,
      onLevel: (level) => {
        live?.level(level)
        useDictation.setState((s) => (s.recording ? { recording: { ...s.recording, level } } : s))
      },
    })
  } catch (error) {
    tracker.stop()
    reportError(fieldId, error instanceof MicrophoneError ? error.problem : 'failed')
    return
  }
  const onKey = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') return
    event.preventDefault()
    event.stopPropagation()
    cancelDictation()
  }
  window.addEventListener('keydown', onKey, true)
  const limit = options.maxSeconds * 1000
  const timers = [
    setTimeout(
      () =>
        useDictation.setState((s) =>
          s.recording ? { recording: { ...s.recording, nearLimit: true } } : s,
        ),
      Math.max(0, limit - WARNING_SECONDS * 1000),
    ),
    setTimeout(() => void stopDictation(), limit),
  ]
  if (recording.peek) live = new LiveTranscript(field, tracker.read(), recording)
  const current = live
  session = {
    fieldId,
    field,
    recording,
    tracker,
    mode: options.mode,
    startedAt: Date.now(),
    timers,
    onKey,
    live,
    ticker: current ? setInterval(() => current.tick(), TICK_MS) : null,
  }
  useDictation.setState({
    recording: {
      fieldId,
      startedAt: session.startedAt,
      level: 0,
      mode: options.mode,
      nearLimit: false,
    },
  })
  void warmUp().catch(() => undefined) // the model loads while the person talks
}

function endSession(): Session | null {
  const ended = session
  if (!ended) return null
  session = null
  if (ended.ticker) clearInterval(ended.ticker)
  for (const timer of ended.timers) clearTimeout(timer)
  window.removeEventListener('keydown', ended.onKey, true)
  useDictation.setState({ recording: null })
  return ended
}

/** Ends the recording and sends it to be transcribed. */
export async function stopDictation(): Promise<void> {
  const ended = endSession()
  if (!ended) return
  const heldFor = Date.now() - ended.startedAt
  if (ended.mode === 'hold' && heldFor < MIN_HOLD_MS) {
    ended.recording.cancel()
    ended.tracker.stop()
    ended.live?.discard()
    return
  }
  // Live: the microphone is released now; the rest of the audio is read when the job runs.
  if (ended.live) await ended.live.end()
  const wav = ended.live ? null : await ended.recording.stop()
  const job: Job = {
    id: nextJobId++,
    fieldId: ended.fieldId,
    field: ended.field,
    wav,
    live: ended.live,
    tracker: ended.tracker,
  }
  queue.push(job)
  useDictation.setState((s) => ({
    jobs: [...s.jobs, { id: job.id, fieldId: job.fieldId, status: 'queued' }],
  }))
  void drain()
}

/** Throws the recording away; nothing is transcribed. */
export function cancelDictation(): void {
  const ended = endSession()
  if (!ended) return
  ended.recording.cancel()
  ended.tracker.stop()
  ended.live?.discard()
}

function finish(job: Job): void {
  job.tracker.stop()
  useDictation.setState((s) => ({ jobs: s.jobs.filter((j) => j.id !== job.id) }))
}

async function drain(): Promise<void> {
  if (running) return
  running = true
  try {
    for (let job = queue.shift(); job; job = queue.shift()) {
      useDictation.setState((s) => ({
        jobs: s.jobs.map((j) => (j.id === job!.id ? { ...j, status: 'transcribing' } : j)),
      }))
      try {
        if (job.live) {
          const text = await job.live.finish()
          if (!text) {
            job.live.discard()
            reportError(job.fieldId, 'no_speech')
          } else if (!job.live.deliver(text)) toClipboard(text)
        } else {
          const result = await transcribe(job.wav!)
          deliver(job, result.text)
        }
      } catch (error) {
        // What was already fixed and shown stays; only the last piece is lost.
        job.live?.keep()
        if (error instanceof ApiError) reportError(job.fieldId, error.code, error.message)
        else reportError(job.fieldId, 'failed', error instanceof Error ? error.message : undefined)
      }
      finish(job)
    }
  } finally {
    running = false
  }
}

/** The text goes where the cursor was; if that field is gone, to the clipboard. */
function deliver(job: Job, text: string): void {
  if (job.field.isConnected) {
    insertText(job.field, job.tracker.read(), text)
    return
  }
  toClipboard(text)
}

function toClipboard(text: string): void {
  void navigator.clipboard?.writeText(text).catch(() => undefined)
  toast.info(i18n.t('dictation.copied'))
}
