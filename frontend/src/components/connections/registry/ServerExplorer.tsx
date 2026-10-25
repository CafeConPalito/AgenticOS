import { CircleCheck, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type ServerCard,
  useCheckUpdates,
  useRegistrySources,
  useServerSearch,
} from '@/api/connections'
import { EmptyState } from '@/components/EmptyState'
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
import { relativeTime } from '@/lib/time'
import { ServerSheet } from './ServerSheet'

const ANY = '__any__'
const compact = new Intl.NumberFormat('es', { notation: 'compact', maximumFractionDigits: 1 })

function Card({ card, onOpen }: { card: ServerCard; onOpen: () => void }) {
  const { t } = useTranslation()
  return (
    <article className="flex flex-col gap-2 rounded-xl border border-sep p-3.5 shadow-card bg-card-grad">
      <button
        type="button"
        onClick={onOpen}
        aria-label={t('connections.explore.open', { name: card.name })}
        className="min-w-0 text-left"
      >
        <span className="block truncate font-mono text-[13px] font-medium">{card.name}</span>
        <span className="line-clamp-2 text-[12.5px] text-muted-foreground">{card.description}</span>
      </button>
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted-foreground">
        <span className="rounded bg-subtle px-1.5">{card.author}</span>
        {card.transport && (
          <span className="rounded bg-subtle px-1.5">
            {t(`connections.explore.transport_${card.transport}`)}
          </span>
        )}
        {card.verified && (
          <span className="bg-status-completed/15 text-status-completed flex items-center gap-1 rounded px-1.5">
            <CircleCheck className="size-3" aria-hidden />
            {t('connections.explore.verified')}
          </span>
        )}
        {card.installed_connection_id && (
          <span className="rounded bg-status-running/15 px-1.5 text-status-running">
            {t('connections.explore.installedChip')}
          </span>
        )}
        <span className="ml-auto">
          {card.uses !== null
            ? t('connections.explore.uses', { count: card.uses, value: compact.format(card.uses) })
            : card.updated_at
              ? relativeTime(card.updated_at)
              : ''}
        </span>
      </div>
    </article>
  )
}

/**
 * «Explorar»: the most used MCP servers of the public registries and a search over them, by name,
 * npm/PyPI package or GitHub address. Nothing is installed without the ficha (spec G).
 */
export function ServerExplorer() {
  const { t } = useTranslation()
  const sources = useRegistrySources()
  const check = useCheckUpdates()
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<string>(ANY)
  const [transport, setTransport] = useState<string>(ANY)
  const [opened, setOpened] = useState<ServerCard | null>(null)
  const listing = useServerSearch(
    query,
    source === ANY ? null : source,
    transport === ANY ? null : transport,
  )
  const errors = Object.entries(listing.data?.errors ?? {})
  const offline = errors.length > 0 && errors.every(([, code]) => code === 'offline')

  async function updates() {
    try {
      const news = await check.mutateAsync()
      toast.success(
        news.length === 0
          ? t('connections.explore.noUpdates')
          : t('connections.explore.updates', { count: news.length }),
      )
    } catch {
      toast.error(t('connections.explore.updatesFailed'))
    }
  }

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <p className="flex items-start gap-2 text-[12.5px] text-muted-foreground">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-status-waiting" aria-hidden />
        {t('connections.explore.warning')}
      </p>
      <form
        role="search"
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(text.trim())
        }}
      >
        <div className="relative min-w-[260px] flex-1">
          <Search className="absolute top-2 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input
            aria-label={t('connections.explore.search')}
            placeholder={t('connections.explore.searchPlaceholder')}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="h-8 pl-8"
          />
        </div>
        <Select value={source} onValueChange={setSource}>
          <SelectTrigger aria-label={t('connections.explore.source')} className="h-8 w-[200px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('connections.explore.allSources')}</SelectItem>
            {(sources.data ?? [])
              .filter((s) => s.switchable && s.enabled)
              .map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.title}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
        <Select value={transport} onValueChange={setTransport}>
          <SelectTrigger aria-label={t('connections.explore.kind')} className="h-8 w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('connections.explore.anyKind')}</SelectItem>
            <SelectItem value="stdio">{t('connections.explore.transport_stdio')}</SelectItem>
            <SelectItem value="http">{t('connections.explore.transport_http')}</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" size="sm">
          {t('connections.explore.searchButton')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={updates}
          disabled={check.isPending}
        >
          <RefreshCw />
          {t('connections.explore.checkUpdates')}
        </Button>
      </form>
      {!query && (
        <h2 className="text-[13px] font-medium text-muted-foreground">
          {t('connections.explore.mostUsed')}
        </h2>
      )}
      {offline && (
        <p role="status" className="rounded-lg bg-subtle p-2.5 text-[13px]">
          {t('connections.explore.offline')}
        </p>
      )}
      {!offline &&
        errors.map(([id, code]) => (
          <p key={id} role="status" className="text-[12.5px] text-status-waiting">
            {t('connections.explore.sourceFailed', {
              source: sources.data?.find((s) => s.id === id)?.title ?? id,
              reason: t(`connections.explore.error_${code}`, { defaultValue: code }),
            })}
          </p>
        ))}
      {listing.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : (listing.data?.cards ?? []).length === 0 ? (
        !offline && (
          <EmptyState
            icon={Search}
            title={t('connections.explore.empty')}
            description={t('connections.explore.emptyHint')}
          />
        )
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
          {(listing.data?.cards ?? []).map((card) => (
            <Card key={`${card.source}-${card.ref}`} card={card} onOpen={() => setOpened(card)} />
          ))}
        </div>
      )}
      <ServerSheet
        source={opened?.source ?? null}
        reference={opened?.ref ?? null}
        onClose={() => setOpened(null)}
      />
    </div>
  )
}
