import { Network, Search } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useExploreKnowledge,
  useKnowledgeGraph,
  useSearchKnowledge,
  type ExploredNode,
} from '@/api/knowledge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

interface Context {
  projectId?: string
  agentId?: string
}

type Mode = 'search' | 'explore' | 'map'

function SearchMode({ projectId, agentId, onOpen }: Context & { onOpen: (docId: string) => void }) {
  const { t } = useTranslation()
  const search = useSearchKnowledge()
  const [query, setQuery] = useState('')

  async function run(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    try {
      await search.mutateAsync({ query: query.trim(), projectId, agentId })
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const result = search.data
  return (
    <>
      <form onSubmit={(e) => void run(e)} className="flex gap-2">
        <Input
          aria-label={t('knowledge.search.label')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('knowledge.search.placeholder')}
        />
        <Button type="submit" variant="outline" disabled={!query.trim() || search.isPending}>
          <Search />
          {t('knowledge.search.run')}
        </Button>
      </form>
      {result && (
        <>
          <p className="text-[12px] text-muted-foreground">
            {t(`knowledge.search.mode.${result.mode}`)}
            {result.model && ` · ${result.model}`}
          </p>
          {result.hits.length === 0 ? (
            <p className="text-muted-foreground">{t('knowledge.search.empty')}</p>
          ) : (
            <ol className="flex flex-col gap-2">
              {result.hits.map((hit) => (
                <li key={`${hit.doc_id}:${hit.chunk}`} className="rounded-lg border p-3">
                  <button
                    type="button"
                    onClick={() => onOpen(hit.doc_id)}
                    className="text-left text-[13px] font-medium underline-offset-2 hover:underline"
                  >
                    {hit.title}
                  </button>
                  <div className="text-[11.5px] text-muted-foreground">
                    {[hit.heading, hit.location].filter(Boolean).join(' · ')}
                    {' · '}
                    {t(`knowledge.search.foundBy.${hit.found_by}`)}
                    {hit.via && ` · ${t('knowledge.search.via', { via: hit.via })}`}
                  </div>
                  <p className="mt-1 line-clamp-4 text-[12.5px] whitespace-pre-line">{hit.text}</p>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </>
  )
}

const strength = (value: number) => value.toFixed(2).replace('.', ',')

function ExploreMode({
  projectId,
  agentId,
  onOpen,
  onHighlight,
}: Context & { onOpen: (docId: string) => void; onHighlight?: (ids: string[]) => void }) {
  const { t } = useTranslation()
  const explore = useExploreKnowledge()
  const [text, setText] = useState('')
  const [hops, setHops] = useState('2')

  async function run(event: React.FormEvent) {
    event.preventDefault()
    if (!text.trim()) return
    try {
      await explore.mutateAsync({
        text: text.trim(),
        hops: Number(hops),
        projectId,
        agentId,
      })
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const result = explore.data
  const nodes: ExploredNode[] = result?.nodes ?? []
  return (
    <>
      <form onSubmit={(e) => void run(e)} className="flex flex-wrap gap-2">
        <Input
          aria-label={t('knowledge.search.explore.label')}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('knowledge.search.explore.placeholder')}
          className="min-w-[260px] flex-1"
        />
        <Select value={hops} onValueChange={setHops}>
          <SelectTrigger aria-label={t('knowledge.search.explore.hops')} className="w-[130px]">
            <span className="text-muted-foreground">{t('knowledge.search.explore.hops')}:</span>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {['1', '2', '3'].map((value) => (
              <SelectItem key={value} value={value}>
                {value}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button type="submit" variant="outline" disabled={!text.trim() || explore.isPending}>
          <Network />
          {t('knowledge.search.explore.run')}
        </Button>
      </form>
      {result && result.message && <p className="text-muted-foreground">{result.message}</p>}
      {result && !result.message && nodes.length <= 1 && (
        <p className="text-muted-foreground">{t('knowledge.search.explore.empty')}</p>
      )}
      {nodes.length > 0 && (
        <>
          {onHighlight && (
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onHighlight(nodes.map((n) => n.id))}
              >
                {t('knowledge.search.explore.highlight')}
              </Button>
            </div>
          )}
          <ol className="flex flex-col gap-2">
            {nodes.map((node) => (
              <li key={node.id} className="rounded-lg border p-3">
                <button
                  type="button"
                  onClick={() => onOpen(node.id)}
                  className="text-left text-[13px] font-medium underline-offset-2 hover:underline"
                >
                  {node.title}
                </button>
                <div className="text-[11.5px] text-muted-foreground">
                  {node.depth === 0
                    ? t('knowledge.search.explore.start')
                    : `${t('knowledge.search.explore.hopsReached', { count: node.depth })} · ${t('knowledge.search.explore.strength', { value: strength(node.strength) })}`}
                </div>
                {node.depth > 0 && (
                  <p className="mt-1 text-[12px]">
                    <span className="text-muted-foreground">
                      {t('knowledge.search.explore.path')}:{' '}
                    </span>
                    {node.path.map((title, index) => (
                      <span key={index}>
                        {index > 0 && (
                          <span className="text-muted-foreground">
                            {' '}
                            —{node.reasons[index - 1]}→{' '}
                          </span>
                        )}
                        {title}
                      </span>
                    ))}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  )
}

function MapMode({ projectId, agentId }: Context) {
  const { t } = useTranslation()
  const graph = useKnowledgeGraph({ projectId, agentId })
  if (graph.isPending) return <Skeleton aria-busy className="h-24 rounded-lg" />
  if (graph.isError) return <p className="text-status-failed">{t('knowledge.loadFailed')}</p>
  const topics = graph.data.topics
  const named = new Map(topics.map((topic) => [topic.id, topic]))
  return (
    <>
      <p className="text-[12.5px] text-muted-foreground">{t('knowledge.search.map.intro')}</p>
      {topics.length === 0 ? (
        <p className="text-muted-foreground">{t('knowledge.search.map.empty')}</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {topics.map((topic) => (
            <li key={topic.id} className="rounded-lg border p-3 text-[13px]">
              <span className="font-medium">
                {topic.loose ? t('knowledge.search.map.loose') : topic.name}
              </span>
              <span className="text-muted-foreground">
                {' '}
                · {t('knowledge.search.map.docs', { count: topic.size })}
              </span>
              {topic.neighbors.length > 0 && (
                <div className="text-[12px] text-muted-foreground">
                  {t('knowledge.search.map.near')}:{' '}
                  {topic.neighbors.map((id) => named.get(id)?.name).join('; ')}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </>
  )
}

/**
 * «Probar búsqueda»: what an agent of this level would get. Three ways to try it: a search (with
 * the help of the graph, marked «por el grafo»), an exploration of the graph from a question or a
 * document, and the map of topics it would see.
 */
export function SearchTester({
  projectId,
  agentId,
  onOpen,
  onHighlight,
}: Context & {
  onOpen: (docId: string) => void
  /** Show these documents highlighted in the graph. */
  onHighlight?: (ids: string[]) => void
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('search')
  return (
    <section className="flex flex-col gap-3">
      <div role="group" aria-label={t('knowledge.search.mode.label')} className="flex gap-2">
        {(['search', 'explore', 'map'] as const).map((value) => (
          <Button
            key={value}
            type="button"
            size="sm"
            variant="outline"
            aria-pressed={mode === value}
            onClick={() => setMode(value)}
            className={cn('rounded-full', mode === value && 'border-ring bg-accent')}
          >
            {t(`knowledge.search.mode.${value}`)}
          </Button>
        ))}
      </div>
      {mode === 'search' && <SearchMode projectId={projectId} agentId={agentId} onOpen={onOpen} />}
      {mode === 'explore' && (
        <ExploreMode
          projectId={projectId}
          agentId={agentId}
          onOpen={onOpen}
          onHighlight={onHighlight}
        />
      )}
      {mode === 'map' && <MapMode projectId={projectId} agentId={agentId} />}
    </section>
  )
}
