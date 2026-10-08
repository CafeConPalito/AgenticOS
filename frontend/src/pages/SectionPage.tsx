import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { NAV, type Section } from '@/components/layout/nav'

/** Placeholder layout shared by every section until its phase implements it. */
export function SectionPage({ section }: { section: Section }) {
  const { t } = useTranslation()
  const { icon } = NAV.find((item) => item.id === section) ?? NAV[0]

  return (
    <div className="mx-auto flex max-w-[1640px] flex-col gap-5 px-6 pt-[22px] pb-8">
      <h1 className="text-[22px] leading-[1.3] font-medium tracking-[-0.01em]">
        {t(`pages.${section}.title`)}
      </h1>
      <EmptyState
        icon={icon}
        title={t(`pages.${section}.emptyTitle`)}
        description={t(`pages.${section}.emptyDescription`)}
      >
        <span className="text-xs text-muted-foreground">{t('pages.comingSoon')}</span>
      </EmptyState>
    </div>
  )
}
