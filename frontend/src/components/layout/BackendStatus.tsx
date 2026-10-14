import { useTranslation } from 'react-i18next'
import type { BackendState } from '@/hooks/useHealth'
import { cn } from '@/lib/utils'

const DOT_CLASS: Record<BackendState, string> = {
  connected: 'bg-status-done',
  connecting: 'bg-status-waiting',
  reconnecting: 'bg-status-waiting',
  disconnected: 'bg-status-failed',
  failed: 'bg-status-failed',
}

export function BackendStatus({
  state,
  version,
  compact = false,
}: {
  state: BackendState
  version?: string
  /** Dot only (the label stays for screen readers and as a tooltip). */
  compact?: boolean
}) {
  const { t } = useTranslation()
  const label =
    state === 'connected'
      ? t('backend.connected', { version: version ?? '' })
      : t(`backend.${state}`)

  return (
    <div
      role="status"
      title={label}
      data-state={state}
      className="flex items-center gap-1.5 text-xs whitespace-nowrap text-muted-foreground"
    >
      <span className={cn('size-[7px] shrink-0 rounded-full', DOT_CLASS[state])} />
      {compact ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </div>
  )
}
