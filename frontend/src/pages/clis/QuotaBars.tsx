import { useTranslation } from 'react-i18next'
import type { QuotaWindow } from '@/api/types'
import { useNow } from '@/hooks/use-now'
import { formatPercent } from '@/lib/format'
import { isOver, resetsText, WARN_QUOTA, windowName } from '@/lib/quota'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'

/**
 * The subscription windows of an account (5 h, weekly…), as its CLI's own `/usage` shows them:
 * the share used, when the window resets and how old the reading is. A window the clock has
 * ended shows as reset until a session reads it again.
 */
export function QuotaBars({ windows }: { windows: QuotaWindow[] }) {
  const { t } = useTranslation()
  const now = useNow(30_000)
  if (windows.length === 0)
    return <p className="text-xs text-muted-foreground">{t('accounts.quota.none')}</p>
  return (
    <ul aria-label={t('accounts.quota.label')} className="flex flex-col gap-2.5">
      {windows.map((window) => {
        const over = isOver(window, now.getTime())
        const used = over ? 0 : window.used_pct
        const warn = used >= WARN_QUOTA
        return (
          <li key={window.id} className="flex flex-col gap-1">
            <div className="flex items-baseline gap-2 text-[12.5px]">
              <span className="font-medium">{windowName(window.id)}</span>
              <span
                className={cn(
                  'ml-auto font-mono text-xs',
                  warn ? 'text-status-waiting' : 'text-muted-foreground',
                )}
              >
                {formatPercent(used / 100)}
              </span>
            </div>
            <span
              role="progressbar"
              aria-label={windowName(window.id)}
              aria-valuenow={Math.round(used)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="relative h-1.5 overflow-hidden rounded-full bg-muted"
            >
              <span
                className={cn(
                  'absolute inset-y-0 left-0 rounded-full',
                  warn ? 'bg-status-waiting' : 'bg-muted-foreground',
                )}
                style={{ width: `${Math.min(used, 100)}%` }}
              />
            </span>
            <span className="text-[11.5px] text-muted-foreground">
              {over
                ? t('accounts.quota.reset')
                : `${resetsText(window, now.getTime())} · ${t('accounts.quota.readAgo', { time: relativeTime(window.read_at, now) })}`}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
