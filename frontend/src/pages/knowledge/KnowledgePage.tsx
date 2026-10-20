import { useTranslation } from 'react-i18next'
import { KnowledgeLibrary } from '@/components/knowledge/KnowledgeLibrary'

/** The general library: what every agent in every project can use. */
export default function KnowledgePage() {
  const { t } = useTranslation()
  return (
    <div className="mx-auto flex max-w-[1080px] flex-col">
      <header className="px-6 pt-[22px]">
        <h1 className="text-[22px] leading-[1.3] font-medium tracking-[-0.01em]">
          {t('knowledge.title')}
        </h1>
      </header>
      <KnowledgeLibrary level={{ scope: 'general' }} />
    </div>
  )
}
