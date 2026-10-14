import { useQueryClient } from '@tanstack/react-query'
import { Check, Play, RotateCcw, SquareTerminal, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import {
  inboxKeys,
  useAnswerItem,
  useDismissItem,
  usePermissionItem,
  useResumeItem,
  useReviewItem,
} from '@/api/inbox'
import { taskKeys } from '@/api/tasks'
import type { InboxItem } from '@/api/types'
import { useDock } from '@/components/terminal/dock-store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { ResumeTaskSession } from '@/pages/runs/ResumeSession'

/** What can be done with a pending request, by kind. Shared by Inicio, Peticiones and the task. */
export function RequestActions({ item }: { item: InboxItem }) {
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
