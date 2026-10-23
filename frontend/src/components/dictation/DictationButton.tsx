import { Loader2, Mic, MicOff, Square } from 'lucide-react'
import { useEffect, useId, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { useDictationSettings, useDictationStatus } from '@/api/dictation'
import { useNow } from '@/hooks/use-now'
import {
  clearError,
  registerField,
  startDictation,
  stopDictation,
} from '@/lib/dictation/controller'
import type { Field } from '@/lib/dictation/insert'
import { cn } from '@/lib/utils'
import { phaseOf, useDictation } from '@/stores/dictation'
import { useUiPrefs } from '@/stores/ui-prefs'

function clock(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/** The microphone of a text field: click to start and again to stop, or hold the shortcut. It
 * shows the level and the time while recording, and tells assistive technology what is going on.
 * Not shown when dictation is turned off. */
export function DictationButton({
  target,
  className,
}: {
  target: RefObject<Field | null>
  className?: string
}) {
  const { t } = useTranslation()
  const id = useId()
  const status = useDictationStatus().data
  const maxSeconds = useDictationSettings().data?.max_seconds ?? 300
  const deviceId = useUiPrefs((s) => s.microphoneId)
  const phase = useDictation((s) => phaseOf(s, id))
  const recording = useDictation((s) => (s.recording?.fieldId === id ? s.recording : null))
  const error = useDictation((s) => s.errors[id])
  const now = useNow(recording ? 500 : null)
  const enabled = Boolean(status?.enabled)

  useEffect(() => {
    const field = target.current
    if (!field || !enabled) return
    return registerField(id, field)
  }, [id, target, enabled])

  if (!enabled) return null

  const busy = phase === 'queued' || phase === 'transcribing'
  const label =
    phase === 'recording'
      ? t('dictation.stop')
      : busy
        ? t(phase === 'queued' ? 'dictation.queued' : 'dictation.transcribing')
        : t('dictation.start')
  const announcement =
    phase === 'recording'
      ? t('dictation.recording')
      : busy
        ? t(phase === 'queued' ? 'dictation.queued' : 'dictation.transcribing')
        : error
          ? t(`dictation.errors.${error.code}`, { defaultValue: error.message ?? error.code })
          : ''

  function onClick() {
    if (phase === 'recording') {
      void stopDictation()
      return
    }
    if (busy) return
    clearError(id)
    if (status && !status.ready && status.reason !== 'disabled') {
      useDictation.getState().setDownloadOpen(true)
      return
    }
    void startDictation(id, { mode: 'click', maxSeconds, deviceId: deviceId ?? undefined })
  }

  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      {recording && (
        <span
          className={cn(
            'flex items-center gap-1.5 rounded-full bg-destructive/10 px-2 py-0.5 text-[11.5px] text-destructive tabular-nums',
            recording.nearLimit && 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
          )}
        >
          <span
            aria-hidden
            className="h-1.5 w-8 overflow-hidden rounded-full bg-current/20"
            data-testid="dictation-level"
          >
            <span
              className="block h-full rounded-full bg-current transition-[width] duration-75"
              style={{ width: `${Math.round(recording.level * 100)}%` }}
            />
          </span>
          {clock(Math.max(0, now.getTime() - recording.startedAt))}
          {recording.nearLimit && <span>{t('dictation.nearLimit')}</span>}
        </span>
      )}
      <button
        type="button"
        aria-label={label}
        aria-pressed={phase === 'recording'}
        title={error ? undefined : label}
        data-phase={phase}
        disabled={busy}
        // The field keeps the focus and its selection while the microphone is used.
        onMouseDown={(event) => event.preventDefault()}
        onClick={onClick}
        className={cn(
          'flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-wait',
          phase === 'recording' &&
            'bg-destructive text-white hover:bg-destructive/90 hover:text-white',
          phase === 'error' && 'text-destructive',
        )}
      >
        {phase === 'recording' ? (
          <Square className="size-3.5 fill-current" />
        ) : busy ? (
          <Loader2 className="size-4 animate-spin" />
        ) : phase === 'error' ? (
          <MicOff className="size-4" />
        ) : (
          <Mic className="size-4" />
        )}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
    </span>
  )
}
