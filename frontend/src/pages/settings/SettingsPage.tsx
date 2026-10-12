import { useTranslation } from 'react-i18next'
import { PageContainer, PageHeader } from '@/components/page'
import { CleanupSection } from './CleanupSection'
import { CliSection } from './CliSection'
import { GeneralSection } from './GeneralSection'
import { LimitsSection } from './LimitsSection'
import { NotificationsSection } from './NotificationsSection'

/** Ajustes (design `12-ajustes`): CLIs, general, notifications, limits, cleanup and about. */
export default function SettingsPage() {
  const { t } = useTranslation()
  return (
    <PageContainer narrow>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />
      <CliSection />
      <div className="grid items-start gap-[22px] lg:grid-cols-2">
        <GeneralSection />
        <NotificationsSection />
      </div>
      <LimitsSection />
      <CleanupSection />
    </PageContainer>
  )
}
