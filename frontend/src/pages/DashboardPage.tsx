import { LayoutDashboard } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { CliReadinessBanner } from '@/components/CliReadinessBanner'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer } from '@/components/page'
import { TodayUsageCard } from '@/components/usage/TodayUsageCard'

/** The rest of the Dashboard (agents, approvals, activity) comes in a later phase. */
export default function DashboardPage() {
  const { t } = useTranslation()
  return (
    <PageContainer>
      <h1 className="text-[22px] leading-[1.3] font-medium tracking-[-0.01em]">
        {t('pages.dashboard.title')}
      </h1>
      <CliReadinessBanner />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <EmptyState
          icon={LayoutDashboard}
          title={t('pages.dashboard.emptyTitle')}
          description={t('pages.dashboard.emptyDescription')}
        >
          <span className="text-xs text-muted-foreground">{t('pages.comingSoon')}</span>
        </EmptyState>
        <TodayUsageCard />
      </div>
    </PageContainer>
  )
}
