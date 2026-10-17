import { useTranslation } from 'react-i18next'
import type { ChangesTotals } from '@/api/types'
import { cn } from '@/lib/utils'

/** «4 ficheros · +120 −35», or just «+120 −35» when compact (a table cell). */
export function ChangesBadge({
  totals,
  compact = false,
  className,
}: {
  totals: ChangesTotals | null | undefined
  compact?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  if (!totals) return null
  return (
    <span
      className={cn(
        'inline-flex items-baseline gap-1.5 font-mono text-xs whitespace-nowrap text-muted-foreground',
        className,
      )}
    >
      {!compact && (
        <span className="font-sans">
          {t('changes.files', { count: totals.files })}
          <span aria-hidden> ·</span>
        </span>
      )}
      <span className="text-[var(--diff-add-fg)]">+{totals.additions}</span>
      <span className="text-[var(--diff-del-fg)]">−{totals.deletions}</span>
    </span>
  )
}
