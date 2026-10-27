import { History, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { type AgentChange, useConfigHistory } from '@/api/architect'
import { useRuns } from '@/api/runs'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/time'
import { fieldLabel } from '@/pages/architect/ArchitectChat'
import { RunsTable } from '@/pages/runs/RunsTable'

export function HistoryTab({ agentId }: { agentId: string }) {
  const { t } = useTranslation()
  const { data: runs, isPending } = useRuns({ agentId })
  const { data: changes } = useConfigHistory(agentId)
  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 px-6 pt-5 pb-8">
      {changes && changes.length > 0 && (
        <section aria-labelledby="config-history">
          <h2 id="config-history" className="mb-2 text-[15px] font-medium">
            {t('agents.configHistory.title')}
          </h2>
          <ol className="flex flex-col divide-y divide-sep rounded-lg border border-sep">
            {changes.map((change) => (
              <ChangeLine key={change.id} change={change} />
            ))}
          </ol>
        </section>
      )}
      <section>
        {isPending ? (
          <Skeleton aria-busy className="h-32 rounded-lg" />
        ) : runs && runs.length > 0 ? (
          <RunsTable runs={runs} showAgent={false} />
        ) : (
          <EmptyState icon={History} title={t('runs.agentHistoryEmpty')} />
        )}
      </section>
    </div>
  )
}

/** «El Arquitecto cambió rol e instrucciones · hace 2 h · ver la conversación». */
function ChangeLine({ change }: { change: AgentChange }) {
  const { t } = useTranslation()
  const names =
    change.source === 'user'
      ? ((change.fields.fields as string[] | undefined) ?? [])
      : Object.keys(change.fields).filter((k) => k !== 'created' && k !== 'imported')
  const what =
    'created' in change.fields
      ? t('agents.configHistory.created')
      : 'imported' in change.fields
        ? t('agents.configHistory.imported')
        : names.map((n) => fieldLabel(t, n)).join(', ')
  return (
    <li className="flex items-center gap-2 px-3 py-2 text-[13px]">
      {change.source !== 'user' && <Sparkles className="size-3.5 text-status-review" aria-hidden />}
      <span className="min-w-0 flex-1">
        {t(`agents.configHistory.source.${change.source}`)} · {what}
      </span>
      {change.conversation_id && (
        <Link
          to={`/agentes/arquitecto/${change.conversation_id}`}
          className="text-[12px] underline"
        >
          {t('proposals.openConversation')}
        </Link>
      )}
      <span className="text-[12px] text-muted-foreground">{relativeTime(change.created_at)}</span>
    </li>
  )
}
