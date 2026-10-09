import { useTranslation } from 'react-i18next'
import type { BackendState } from '@/hooks/useHealth'
import { cn } from '@/lib/utils'

const DOT_CLASS: Record<BackendState, string> = {
  connected: 'bg-status-done',
  connecting: 'bg-status-waiting',
  disconnected: 'bg-status-failed',
}

export function BackendStatus({
  state,
  version,
  compact = false,
}: {
  state: BackendState
  version?: string
  compact?: boolean
}) {
  const { t } = useTranslation()
  const label =
    state === 'connected'
      ? t('backend.connected', { version: version ?? '' })
      : state === 'connecting'
        ? t('backend.connecting')
        : t('backend.disconnected')

  return (
    <div
      role="status"
      title={label}
      data-state={state}
      className="flex h-8 items-center gap-[9px] px-2.5 text-xs whitespace-nowrap text-sidebar-muted"
    >
      <span className={cn('size-2 shrink-0 rounded-full', DOT_CLASS[state])} />
      {compact ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </div>
  )
}
