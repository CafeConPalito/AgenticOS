import { MessagesSquare, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  type ConversationCreate,
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
} from '@/api/architect'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useArchitectEvents } from '@/lib/architect-events'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'
import { ArchitectChat } from './ArchitectChat'
import { SheetPanel } from './SheetPanel'

/** «Crear con el Arquitecto» (phase 19, design §11): `/agentes/arquitecto` lists the
 * conversations (and starts one with `?nueva`, or improves an agent with `?mejorar=<id>`);
 * `/agentes/arquitecto/<id>` is one conversation, chat on the left and the sheet on the right. */
export default function ArchitectPage() {
  const { conversationId } = useParams()
  return conversationId ? <Workspace id={conversationId} /> : <Conversations />
}

function Conversations() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { data, isPending } = useConversations()
  const create = useCreateConversation()
  const remove = useDeleteConversation()
  const started = useRef(false)

  async function start(body: ConversationCreate) {
    try {
      const created = await create.mutateAsync(body)
      navigate(`/agentes/arquitecto/${created.id}`, { replace: true })
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  // `?nueva` and `?mejorar=<agent>` (from Agentes, Inicio, the palette, an agent's editor).
  // `?equipo` starts a new team, `?equipo=<id>` improves one, `?pipeline=<project>` a pipeline.
  const improve = params.get('mejorar')
  const team = params.get('equipo')
  const pipeline = params.get('pipeline')
  const fresh = params.has('nueva') || params.has('equipo')
  const requested = Boolean(improve || pipeline || fresh)
  useEffect(() => {
    if (started.current || !requested) return
    started.current = true
    void start(
      improve
        ? { mode: 'improve_agent', agent_id: improve }
        : pipeline
          ? { mode: 'improve_pipeline', project_id: pipeline }
          : team
            ? { mode: 'improve_team', team_id: team }
            : params.has('equipo')
              ? { mode: 'team' }
              : { mode: 'agent' },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested])

  return (
    <PageContainer narrow>
      <PageHeader
        title={t('architect.title')}
        subtitle={t('architect.subtitle')}
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => void start({ mode: 'team' })}
              disabled={create.isPending}
            >
              <Plus />
              {t('architect.newTeam')}
            </Button>
            <Button
              onClick={() => void start({ mode: 'agent' })}
              disabled={create.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              <Plus />
              {t('architect.new')}
            </Button>
          </div>
        }
      />
      {isPending || requested ? (
        <Skeleton aria-busy className="h-32 rounded-lg" />
      ) : data && data.length > 0 ? (
        <ul className="flex flex-col divide-y divide-sep rounded-lg border border-sep">
          {data.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-4 py-3">
              <Sparkles className="size-4 shrink-0 text-status-review" aria-hidden />
              <Link to={`/agentes/arquitecto/${c.id}`} className="min-w-0 flex-1 hover:underline">
                <span className="block truncate font-medium">
                  {c.title || t('architect.untitled')}
                </span>
                <span className="text-[12.5px] text-muted-foreground">
                  {t(`architect.modes.${c.mode}`)} · {t(`architect.status.${c.status}`)} ·{' '}
                  {relativeTime(c.updated_at)}
                </span>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('architect.delete')}
                onClick={() =>
                  remove.mutate(c.id, { onError: (error) => toast.error(errorMessage(error)) })
                }
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={MessagesSquare}
          title={t('architect.emptyTitle')}
          description={t('architect.emptyDescription')}
        />
      )}
    </PageContainer>
  )
}

function Workspace({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data: conversation, isPending, isError } = useConversation(id)
  // The reply of the turn in progress, block by block, until its message arrives.
  const [blocks, setBlocks] = useState<string[]>([])

  useArchitectEvents(id, setBlocks)

  if (isPending)
    return (
      <PageContainer>
        <Skeleton aria-busy className="h-[60vh] rounded-lg" />
      </PageContainer>
    )
  if (isError || !conversation)
    return (
      <PageContainer>
        <EmptyState icon={MessagesSquare} title={t('architect.notFound')} />
      </PageContainer>
    )
  return (
    <div className="grid h-full min-h-[560px] grid-cols-[minmax(0,1fr)_minmax(380px,0.9fr)]">
      <ArchitectChat conversation={conversation} blocks={blocks} />
      <SheetPanel conversation={conversation} />
    </div>
  )
}
