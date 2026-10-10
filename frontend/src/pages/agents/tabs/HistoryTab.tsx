import { History } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRuns } from '@/api/runs'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { RunsTable } from '@/pages/runs/RunsTable'

export function HistoryTab({ agentId }: { agentId: string }) {
  const { t } = useTranslation()
  const { data: runs, isPending } = useRuns({ agentId })
  return (
    <div className="mx-auto w-full max-w-[1100px] px-6 pt-5 pb-8">
      {isPending ? (
        <Skeleton aria-busy className="h-32 rounded-lg" />
      ) : runs && runs.length > 0 ? (
        <RunsTable runs={runs} showAgent={false} />
      ) : (
        <EmptyState icon={History} title={t('runs.agentHistoryEmpty')} />
      )}
    </div>
  )
}
