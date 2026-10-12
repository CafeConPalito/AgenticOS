import { useTranslation } from 'react-i18next'
import { PageContainer, PageHeader } from '@/components/page'
import { CliSection } from './CliSection'
import { LimitsSection } from './LimitsSection'
import { NotificationsSection } from './NotificationsSection'

/** Ajustes (design `12-ajustes`): CLIs, general, notifications, limits, cleanup and about. */
export default function SettingsPage() {
  const { t } = useTranslation()
  return (
    <PageContainer narrow>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />
      <CliSection />
      <NotificationsSection />
      <LimitsSection />
    </PageContainer>
  )
}
