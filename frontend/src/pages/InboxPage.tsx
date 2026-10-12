import { useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  BatteryWarning,
  Check,
  CheckCheck,
  Clock,
  HelpCircle,
  Inbox,
  OctagonAlert,
  Gauge,
  PackageCheck,
  Play,
  RotateCcw,
  ShieldCheck,
  SquareTerminal,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  inboxKeys,
  useAnswerItem,
  useDismissItem,
  useInbox,
  useInboxSummary,
  usePermissionItem,
  useResumeItem,
  useReviewItem,
} from '@/api/inbox'
import { taskKeys } from '@/api/tasks'
import type { InboxItem, InboxKind } from '@/api/types'
import { AgentAvatar, ProjectChip } from '@/components/agentic/primitives'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { useDock } from '@/components/terminal/dock-store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { relativeTime } from '@/lib/time'
import { ResumeTaskSession } from '@/pages/runs/ResumeSession'
import { cn } from '@/lib/utils'

const PROMPT = '❯ '

const KIND_STYLE: Record<InboxKind, { color: string; icon: typeof Inbox }> = {
  approval: { color: 'var(--status-waiting)', icon: ShieldCheck },
  question: { color: 'var(--status-running)', icon: HelpCircle },
  blocker: { color: 'var(--status-failed)', icon: OctagonAlert },
  review: { color: 'var(--status-review)', icon: CheckCheck },
  stalled: { color: 'var(--status-waiting)', icon: Clock },
  attention: { color: 'var(--status-failed)', icon: AlertTriangle },
  delivery: { color: 'var(--status-done)', icon: PackageCheck },
  limit: { color: 'var(--status-waiting)', icon: Gauge },
  quota: { color: 'var(--status-failed)', icon: BatteryWarning },
}

export default function InboxPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const view = params.get('vista') === 'resueltas' ? 'resolved' : 'pending'
  const items = useInbox(view)
  const summary = useInboxSummary().data
  const focused = params.get('item')

  useEffect(() => {
    if (focused) document.getElementById(`inbox-${focused}`)?.scrollIntoView({ block: 'center' })
  }, [focused, items.data])

  return (
    <PageContainer>
      <div className="mx-auto flex w-full max-w-[1080px] flex-col gap-5">
        <PageHeader
          title={t('inbox.title')}
          subtitle={t('inbox.subtitle')}
          actions={
            <div role="tablist" className="flex rounded-lg border bg-subtle p-0.5">
              {(['pending', 'resolved'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={view === v}
                  onClick={() =>
                    setParams(v === 'pending' ? {} : { vista: 'resueltas' }, { replace: true })
                  }
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-[13px] text-muted-foreground',
                    view === v && 'bg-card font-medium text-foreground shadow-sm',
                  )}
                >
                  {t(`inbox.${v}`)}
                  <span className="font-mono text-[11px]">{summary?.[v] ?? ''}</span>
                </button>
              ))}
            </div>
          }
        />
        {items.data && items.data.length === 0 ? (
          view === 'pending' ? (
            <EmptyState
              icon={Inbox}
              title={t('inbox.emptyTitle')}
              description={t('inbox.emptyDescription')}
            />
          ) : (
            <p className="text-sm text-muted-foreground">{t('inbox.emptyResolved')}</p>
          )
        ) : (
          <ul className="flex flex-col gap-4">
            {(items.data ?? []).map((item) => (
              <li key={item.id} id={`inbox-${item.id}`}>
                <InboxCard item={item} focused={item.id === focused} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </PageContainer>
  )
}

function InboxCard({ item, focused }: { item: InboxItem; focused: boolean }) {
  const { t } = useTranslation()
  const style = KIND_STYLE[item.kind]
  const Icon = style.icon
  const title = item.kind === 'approval' ? t('inbox.approvalTitle') : item.title
  return (
    <article
      aria-label={`${t(`inbox.kinds.${item.kind}`)}: ${title}`}
      className={cn(
        'overflow-hidden rounded-xl border bg-card',
        focused && 'border-ring ring-1 ring-ring',
      )}
    >
      <div className="flex gap-3 px-4 py-3.5">
        <div className="relative h-fit">
          <AgentAvatar name={item.agent_name || '?'} color={item.agent_color} size={34} />
          <span
            className="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full border bg-card"
            style={{ color: style.color }}
          >
            <Icon className="size-2.5" />
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
            <span className="font-medium" style={{ color: style.color }}>
              {t(`inbox.kinds.${item.kind}`)}
            </span>
            {item.agent_name && (
              <>
                · <span className="font-medium text-foreground">{item.agent_name}</span>
              </>
            )}
            {item.project_name && (
              <>
                · <ProjectChip name={item.project_name} color={item.project_color} variant="dot" />
              </>
            )}
            {item.task_id && (
              <>
                ·{' '}
                <Link to={`/tablero/tareas/${item.task_id}`} className="text-ring hover:underline">
                  {item.task_code ? `${item.task_code} · ${item.task_title ?? ''}` : ''}
                </Link>
              </>
            )}
            <time className="ml-auto" dateTime={item.created_at}>
              {relativeTime(item.created_at)}
            </time>
          </div>
          <h2 className="mt-1 text-[15px] font-medium">{title}</h2>
          {item.kind === 'approval' && item.command && (
            <pre className="mt-2 overflow-x-auto rounded-md bg-terminal px-3 py-2 font-mono text-[13px] text-terminal-foreground">
              <span aria-hidden className="text-[#7F8DAA]">
                {PROMPT}
              </span>
              {item.command}
            </pre>
          )}
          {item.detail && (
            <p className="mt-1.5 text-[13px] whitespace-pre-wrap text-muted-foreground">
              {item.detail}
            </p>
          )}
          {item.status === 'resolved' && item.resolution && (
            <p className="mt-2 text-[13px] text-status-done">
              {t(`inbox.resolution.${item.resolution}`, { text: item.response ?? '' })}
            </p>
          )}
        </div>
      </div>
      {item.status === 'pending' && <InboxActions item={item} />}
    </article>
  )
}

function InboxActions({ item }: { item: InboxItem }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const showDock = useDock((s) => s.show)
  const answer = useAnswerItem()
  const permission = usePermissionItem()
  const review = useReviewItem()
  const dismiss = useDismissItem()
  const resume = useResumeItem()
  const [text, setText] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const busy =
    answer.isPending ||
    permission.isPending ||
    review.isPending ||
    dismiss.isPending ||
    resume.isPending
  const onError = (error: unknown) => toast.error(errorMessage(error))

  async function retryTask() {
    try {
      await api.post(`/api/tasks/${item.task_id}/retry`)
      await queryClient.invalidateQueries({ queryKey: inboxKeys.all })
      await queryClient.invalidateQueries({ queryKey: taskKeys.all })
      toast.success(t('inbox.toast.done'))
    } catch (error) {
      onError(error)
    }
  }

  const reply = (value: string) =>
    answer.mutate(
      { id: item.id, text: value },
      {
        onSuccess: () => toast.success(t('inbox.toast.answered', { name: item.agent_name })),
        onError,
      },
    )

  return (
    <div className="flex flex-wrap items-center gap-2 border-t bg-subtle px-4 py-2.5">
      {item.kind === 'approval' && (
        <>
          <Button
            size="sm"
            disabled={busy}
            onClick={() =>
              permission.mutate(
                { id: item.id, approve: true },
                { onSuccess: () => toast.success(t('inbox.toast.approved')), onError },
              )
            }
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Check />
            {t('inbox.approve')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() =>
              permission.mutate(
                { id: item.id, approve: false },
                { onSuccess: () => toast.success(t('inbox.toast.rejected')), onError },
              )
            }
          >
            {t('inbox.reject')}
          </Button>
        </>
      )}
      {(item.kind === 'question' || item.kind === 'blocker') && (
        <form
          className="flex flex-1 flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (text.trim()) reply(text.trim())
          }}
        >
          {item.options.map((option) => (
            <Button
              key={option}
              type="button"
              size="sm"
              variant="outline"
              className="rounded-full"
              onClick={() => setText(option)}
            >
              {option}
            </Button>
          ))}
          <Input
            aria-label={t('inbox.answerPlaceholder')}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t('inbox.answerPlaceholder')}
            className="h-8 min-w-[220px] flex-1"
          />
          <Button
            type="submit"
            size="sm"
            disabled={busy || !text.trim()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('inbox.answer')}
          </Button>
        </form>
      )}
      {item.kind === 'review' && !rejecting && (
        <>
          <Button
            size="sm"
            disabled={busy}
            onClick={() =>
              review.mutate(
                { id: item.id, approve: true },
                { onSuccess: () => toast.success(t('inbox.toast.approved')), onError },
              )
            }
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Check />
            {t('inbox.reviewApprove')}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setRejecting(true)}>
            <X />
            {t('inbox.reviewReject')}
          </Button>
        </>
      )}
      {item.kind === 'review' && rejecting && (
        <form
          className="flex flex-1 items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            review.mutate(
              { id: item.id, approve: false, reason: text.trim() },
              { onSuccess: () => toast.success(t('inbox.toast.rejected')), onError },
            )
          }}
        >
          <Input
            aria-label={t('inbox.reasonPlaceholder')}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t('inbox.reasonPlaceholder')}
            className="h-8 flex-1"
          />
          <Button type="submit" size="sm" disabled={busy || !text.trim()}>
            {t('inbox.reviewReject')}
          </Button>
        </form>
      )}
      {item.kind === 'quota' && (
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            resume.mutate(item.id, {
              onSuccess: () => toast.success(t('inbox.toast.resumed')),
              onError,
            })
          }
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          <Play />
          {t('inbox.resume')}
        </Button>
      )}
      {item.kind === 'limit' && (
        <>
          <span className="text-[12.5px] text-muted-foreground">{t('inbox.limitHint')}</span>
          <Button size="sm" variant="outline" asChild>
            <Link to="/ajustes">{t('inbox.openSettings')}</Link>
          </Button>
        </>
      )}
      {item.kind === 'attention' && item.task_id && <ResumeTaskSession taskId={item.task_id} />}
      {item.kind === 'attention' && item.task_id && (
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void retryTask()}>
          <RotateCcw />
          {t('inbox.retry')}
        </Button>
      )}
      {(item.kind === 'stalled' || item.kind === 'attention') && item.task_id && (
        <Button size="sm" variant="outline" asChild>
          <Link to={`/tablero/tareas/${item.task_id}`}>{t('inbox.openTask')}</Link>
        </Button>
      )}
      {item.kind === 'delivery' ? (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => dismiss.mutate(item.id, { onError })}
        >
          {t('inbox.markReviewed')}
        </Button>
      ) : (
        (item.kind === 'stalled' || item.kind === 'attention') && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => dismiss.mutate(item.id, { onError })}
          >
            {t('inbox.dismiss')}
          </Button>
        )
      )}
      {item.run_id && (
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          onClick={() => showDock(item.run_id!)}
        >
          <SquareTerminal />
          {t('inbox.openTerminal')}
        </Button>
      )}
    </div>
  )
}
