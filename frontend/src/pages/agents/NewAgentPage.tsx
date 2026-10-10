import { useTranslation } from 'react-i18next'
import { PageContainer, PageHeader } from '@/components/page'
import { TemplatePicker } from './TemplatePicker'

export default function NewAgentPage() {
  const { t } = useTranslation()
  return (
    <PageContainer>
      <PageHeader title={t('agents.new.title')} subtitle={t('agents.new.subtitle')} />
      <TemplatePicker />
    </PageContainer>
  )
}
