import { AlertTriangle, Search, WifiOff } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type Listing,
  type RegistryCard,
  type RegistryPreview,
  useCheckUpdates,
  usePopularSkills,
  usePreviewSkill,
  useRegistries,
  useSearchSkills,
} from '@/api/skills'
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
import { RegistrySkillSheet } from './RegistrySkillSheet'

const ALL = 'all'
const number = new Intl.NumberFormat('es-ES')

/** «Explorar»: the most used skills of the public registries, search and install (spec D). */
export function RegistryExplorer() {
  const { t } = useTranslation()
  const registries = useRegistries().data ?? []
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [source, setSource] = useState(ALL)
  const [category, setCategory] = useState(ALL)
  const [preview, setPreview] = useState<RegistryPreview | null>(null)
  const popular = usePopularSkills(source === ALL ? null : source)
  const search = useSearchSkills(query, source === ALL ? null : source)
  const open = usePreviewSkill()
  const check = useCheckUpdates()
  const listing: Listing | undefined = query ? search.data : popular.data
  const pending = query ? search.isPending : popular.isPending
  const cards = (listing?.cards ?? []).filter((c) => category === ALL || c.category === category)
  const categories = [...new Set((listing?.cards ?? []).map((c) => c.category).filter(Boolean))]
  const errors = Object.entries(listing?.errors ?? {})
  const offline = errors.length > 0 && errors.every(([, code]) => code === 'offline')
  const sources = registries.filter((r) => r.enabled && r.id !== 'github')

  function show(card: RegistryCard) {
    open.mutate(card, {
      onSuccess: setPreview,
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <p
        role="note"
        className="flex items-start gap-2 rounded-lg border border-status-waiting/40 bg-status-waiting/10 px-3 py-2 text-[12.5px]"
      >
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-status-waiting" aria-hidden />
        {t('skills.explore.warning')}
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          setQuery(draft.trim())
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <div className="relative min-w-[280px] flex-1">
          <Search className="absolute top-2 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input
            aria-label={t('skills.explore.search')}
            placeholder={t('skills.explore.search')}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              if (!e.target.value) setQuery('')
            }}
            className="pl-8"
          />
        </div>
        <Select value={source} onValueChange={setSource}>
          <SelectTrigger aria-label={t('skills.explore.source')} className="h-9 w-[200px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('skills.explore.allSources')}</SelectItem>
            {sources.map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {t(`skills.explore.sources.${r.id}`, { defaultValue: r.title })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {categories.length > 0 && (
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger aria-label={t('skills.explore.category')} className="h-9 w-[170px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t('skills.explore.allCategories')}</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={check.isPending}
          onClick={() =>
            check.mutate(undefined, {
              onSuccess: () => toast.success(t('skills.explore.updates.checked')),
              onError: (error) => toast.error(errorMessage(error)),
            })
          }
        >
          {t('skills.explore.updates.check')}
        </Button>
      </form>
      <h2 className="text-[15px] font-medium">
        {query ? t('skills.explore.results') : t('skills.explore.popular')}
      </h2>
      {offline ? (
        <p role="alert" className="flex items-center gap-2 text-[13px] text-status-waiting">
          <WifiOff className="size-4" aria-hidden />
          {t('skills.explore.offline')}
        </p>
      ) : (
        errors.map(([id, code]) => (
          <p key={id} role="alert" className="text-[12.5px] text-status-waiting">
            {t(`skills.explore.sourceError.${code}`, {
              source: t(`skills.explore.sources.${id}`, { defaultValue: id }),
              defaultValue: `${id}: ${code}`,
            })}
          </p>
        ))
      )}
      {pending ? (
        <Skeleton aria-busy className="h-32 rounded-lg" />
      ) : cards.length === 0 ? (
        !offline && (
          <p className="text-[13px] text-muted-foreground">{t('skills.explore.nothing')}</p>
        )
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
          {cards.map((card) => (
            <li key={`${card.source}:${card.ref}`}>
              <button
                type="button"
                onClick={() => show(card)}
                disabled={open.isPending}
                aria-label={t('skills.explore.open', { name: card.name })}
                className="flex h-full w-full flex-col gap-1.5 rounded-xl border border-sep p-3.5 text-left shadow-card bg-card-grad hover:border-ring"
              >
                <span className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-[13px] font-medium">
                    {card.name}
                  </span>
                  {card.installed_skill_id && (
                    <span className="rounded bg-accent px-1.5 text-[11px]">
                      {t('skills.explore.installed')}
                    </span>
                  )}
                </span>
                {card.description && (
                  <span className="line-clamp-2 text-[12.5px] text-muted-foreground">
                    {card.description}
                  </span>
                )}
                <span className="mt-auto flex flex-wrap gap-x-2 text-[11.5px] text-muted-foreground">
                  <span>
                    {t(`skills.explore.sources.${card.source}`, { defaultValue: card.source })}
                  </span>
                  {card.author && <span>{card.author}</span>}
                  {card.installs !== null && (
                    <span>
                      {t('skills.explore.installs', {
                        count: card.installs,
                        formatted: number.format(card.installs),
                      })}
                    </span>
                  )}
                  {card.installs === null && card.stars !== null && (
                    <span>{t('skills.explore.stars', { count: card.stars })}</span>
                  )}
                  {card.updated_at && <span>{card.updated_at}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {listing?.attribution && (
        <p className="text-[11.5px] text-muted-foreground">{listing.attribution}</p>
      )}
      <RegistrySkillSheet preview={preview} onClose={() => setPreview(null)} />
    </div>
  )
}
