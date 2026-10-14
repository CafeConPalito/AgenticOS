import { useTranslation } from 'react-i18next'
import { isActive } from '@/api/runs'
import type { Run, Task } from '@/api/types'
import { useNow } from '@/hooks/use-now'
import { formatTokensUnit, formatUsd, totalTokens } from '@/lib/format'
import { formatDuration } from '@/lib/time'

/** One line under the live output: the session, how long it ran and what it cost. */
export function SessionFactsLine({ run, task }: { run: Run; task: Task }) {
  const { t } = useTranslation()
  const now = useNow(isActive(run) ? 1000 : null)
  const usage = run.usage
  const cost =
    usage.cost_usd !== null
      ? formatUsd(usage.cost_usd)
      : totalTokens(usage) > 0
        ? formatTokensUnit(totalTokens(usage))
        : '—'
  const facts: [string, string][] = []
  if (run.cli_session_id) facts.push([t('tasks.facts.session'), run.cli_session_id])
  if (run.account_label) facts.push([t('tasks.facts.account'), run.account_label])
  facts.push([t('tasks.facts.duration'), formatDuration(run.started_at, run.ended_at, now)])
  facts.push([t('tasks.facts.cost'), cost])
  if (task.branch) facts.push([t('tasks.facts.branch'), task.branch])
  facts.push([t('tasks.facts.folder'), run.cwd])
  return (
    <dl
      aria-label={t('tasks.facts.label')}
      className="flex flex-wrap gap-x-5 gap-y-1 px-0.5 text-xs text-muted-foreground"
    >
      {facts.map(([label, value]) => (
        <div key={label} className="flex min-w-0 gap-1.5">
          <dt>{label}</dt>
          <dd className="truncate font-mono text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  )
}
