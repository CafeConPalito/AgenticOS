import { useTranslation } from 'react-i18next'
import { isActive } from '@/api/runs'
import type { Run, UsageTotals } from '@/api/types'
import { useNow } from '@/hooks/use-now'
import { formatTokens, formatUsd } from '@/lib/format'
import { formatDuration } from '@/lib/time'

/**
 * «Consumo de la sesión» (design 09a): a 2×3 grid that moves at the end of every turn (the
 * run's WebSocket pushes it), and the CLI's session id. In a task, the total of all its runs.
 */
export function SessionUsage({ run, taskTotal }: { run: Run; taskTotal?: UsageTotals }) {
  const { t } = useTranslation()
  const now = useNow(isActive(run) ? 1000 : null)
  const usage = run.usage
  const unavailable = usage.status === 'unavailable'
  const tokens = (value: number) => (unavailable ? '—' : formatTokens(value))
  const cells: [string, string][] = [
    [t('usage.session.input'), tokens(usage.input_tokens)],
    [t('usage.session.output'), tokens(usage.output_tokens)],
    [t('usage.session.cacheRead'), tokens(usage.cache_read_tokens)],
    [t('usage.session.cacheWrite'), tokens(usage.cache_creation_tokens)],
    [t('usage.session.cost'), formatUsd(usage.cost_usd)],
    [t('usage.session.duration'), formatDuration(run.started_at, run.ended_at, now)],
  ]
  return (
    <section aria-label={t('usage.session.title')} className="mt-5">
      <h2 className="mb-2 text-[12.5px] text-muted-foreground">{t('usage.session.title')}</h2>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border">
        {cells.map(([label, value]) => (
          <div key={label} className="bg-card px-3 py-2">
            <dt className="text-[11.5px] text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 font-mono text-[14px]">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[11.5px] text-muted-foreground">
        {unavailable
          ? t('usage.unavailable')
          : usage.status === 'pending'
            ? t('usage.session.pending')
            : usage.status === 'partial'
              ? t('usage.partialHint')
              : null}
      </p>
      {run.cli_session_id && (
        <p className="mt-1 truncate text-[11.5px] text-muted-foreground">
          {t('usage.session.sessionId')}{' '}
          <span className="font-mono text-foreground">{run.cli_session_id}</span>
        </p>
      )}
      {taskTotal && (
        <p className="mt-1 text-[11.5px] text-muted-foreground">
          {t('usage.session.taskTotal')}{' '}
          <span className="font-mono text-foreground">
            {formatTokens(
              taskTotal.input_tokens +
                taskTotal.output_tokens +
                taskTotal.cache_read_tokens +
                taskTotal.cache_creation_tokens,
            )}{' '}
            · {formatUsd(taskTotal.cost_usd)}
          </span>
        </p>
      )}
    </section>
  )
}
