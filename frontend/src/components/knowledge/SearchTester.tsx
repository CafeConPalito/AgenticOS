import { Search } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useSearchKnowledge } from '@/api/knowledge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/form-errors'

/** «Probar búsqueda»: what an agent of this level would find for a question. */
export function SearchTester({
  projectId,
  agentId,
  onOpen,
}: {
  projectId?: string
  agentId?: string
  onOpen: (docId: string) => void
}) {
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
    <section className="flex flex-col gap-3">
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
                  </div>
                  <p className="mt-1 line-clamp-4 text-[12.5px] whitespace-pre-line">{hit.text}</p>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  )
}
