import { BookOpen } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useKnowledgeDocs, type KnowledgeDoc, type KnowledgeLevel } from '@/api/knowledge'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useKnowledgeEvents } from '@/hooks/use-knowledge-events'
import { cn } from '@/lib/utils'
import { AddDocuments } from './AddDocuments'
import { DocList } from './DocList'
import { DocSheet } from './DocSheet'
import { ResourceMonitor } from './ResourceMonitor'
import { SearchTester } from './SearchTester'

type Filter = 'all' | 'proposed' | 'agent'

const FILTERS: Record<Filter, (doc: KnowledgeDoc) => boolean> = {
  all: () => true,
  proposed: (doc) => doc.review === 'proposed',
  agent: (doc) => doc.origin === 'agent' && doc.review === 'none',
}

/** «Todos · Propuestos (2) · Generados por agentes»: only shown once an agent has contributed. */
function Filters({
  docs,
  value,
  onChange,
}: {
  docs: KnowledgeDoc[]
  value: Filter
  onChange: (next: Filter) => void
}) {
  const { t } = useTranslation()
  if (!docs.some((doc) => doc.origin === 'agent' || doc.review === 'proposed')) return null
  const counted = (filter: Filter) => docs.filter(FILTERS[filter]).length
  return (
    <div role="group" aria-label={t('knowledge.filters.label')} className="flex flex-wrap gap-2">
      {(['all', 'proposed', 'agent'] as const).map((filter) => (
        <Button
          key={filter}
          type="button"
          size="sm"
          variant="outline"
          aria-pressed={value === filter}
          onClick={() => onChange(filter)}
          className={cn('rounded-full', value === filter && 'border-ring bg-accent')}
        >
          {t(`knowledge.filters.${filter}`)}
          {filter !== 'all' && ` (${counted(filter)})`}
        </Button>
      ))}
    </div>
  )
}

/**
 * The library of one level: general, a project's or an agent's. Adding, the list with the state
 * of each document, the machine's load while they are processed, and a search to try it.
 */
export function KnowledgeLibrary({ level }: { level: KnowledgeLevel }) {
  const { t } = useTranslation()
  useKnowledgeEvents()
  const docs = useKnowledgeDocs(level)
  const [opened, setOpened] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const shown = docs.data?.filter(FILTERS[filter]) ?? []

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
          <Filters docs={docs.data} value={filter} onChange={setFilter} />
          <DocList docs={shown} onOpen={setOpened} />
          <SearchTester projectId={level.projectId} agentId={level.agentId} onOpen={setOpened} />
        </>
      )}
      <DocSheet docId={opened} onClose={() => setOpened(null)} onNavigate={setOpened} />
    </div>
  )
}
