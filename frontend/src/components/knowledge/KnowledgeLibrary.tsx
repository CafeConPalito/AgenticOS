import { BookOpen } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useKnowledgeDocs, type KnowledgeLevel } from '@/api/knowledge'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { useKnowledgeEvents } from '@/hooks/use-knowledge-events'
import { AddDocuments } from './AddDocuments'
import { DocList } from './DocList'
import { DocSheet } from './DocSheet'
import { ResourceMonitor } from './ResourceMonitor'
import { SearchTester } from './SearchTester'

/**
 * The library of one level: general, a project's or an agent's. Adding, the list with the state
 * of each document, the machine's load while they are processed, and a search to try it.
 */
export function KnowledgeLibrary({ level }: { level: KnowledgeLevel }) {
  const { t } = useTranslation()
  useKnowledgeEvents()
  const docs = useKnowledgeDocs(level)
  const [opened, setOpened] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <p className="max-w-[760px] text-[13px] text-muted-foreground">
        {t(`knowledge.intro.${level.scope}`)}
      </p>
      <AddDocuments level={level} />
      <ResourceMonitor />
      {docs.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : docs.isError ? (
        <p role="alert" className="text-status-failed">
          {t('knowledge.loadFailed')}
        </p>
      ) : docs.data.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={t('knowledge.empty.title')}
          description={t('knowledge.empty.description')}
        />
      ) : (
        <>
          <DocList docs={docs.data} onOpen={setOpened} />
          <SearchTester projectId={level.projectId} agentId={level.agentId} onOpen={setOpened} />
        </>
      )}
      <DocSheet docId={opened} onClose={() => setOpened(null)} />
    </div>
  )
}
