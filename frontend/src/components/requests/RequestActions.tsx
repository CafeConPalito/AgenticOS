import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftRight,
  BookOpenCheck,
  Check,
  LogIn,
  Play,
  RotateCcw,
  Sparkles,
  SquareTerminal,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  inboxKeys,
  useAnswerItem,
  useDismissItem,
  usePermissionItem,
  useResumeItem,
  useReviewItem,
  useSwitchItem,
} from '@/api/inbox'
import { useProposal } from '@/api/architect'
import { taskKeys } from '@/api/tasks'
import type { InboxItem } from '@/api/types'
import { ChangesButton } from '@/components/changes/ChangesSheet'
import { DocSheet } from '@/components/knowledge/DocSheet'
import { SkillProposalReview } from '@/components/skills/SkillProposalReview'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { ResumeTaskSession } from '@/pages/runs/ResumeSession'

/** What can be done with a pending request, by kind. Shared by Inicio, Peticiones and the task. */
/** A reply that grows with what is written (up to a few lines) and can be dictated: Enter
 * sends it, Shift+Enter starts a new line. */
function GrowingField({
  value,
  onChange,
  containerClassName,
  canSubmit,
  ...props
}: {
  value: string
  onChange: (value: string) => void
  containerClassName?: string
  /** Enter sends only when this is true (text written and nothing in flight). */
  canSubmit: boolean
  'aria-label': string
  placeholder: string
}) {
  return (
    <Textarea
      {...props}
      dictation
      containerClassName={containerClassName}
      rows={1}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
          e.preventDefault()
          if (canSubmit) e.currentTarget.form?.requestSubmit()
        }
      }}
      className="max-h-40 min-h-8 resize-none py-1 text-[13px] md:text-[13px]"
    />
  )
}

export function RequestActions({
  item,
  inline = false,
  extra,
  hideChanges = false,
  onDone,
}: {
  item: InboxItem
  /** No footer bar: the actions sit inside the item (Inicio). */
  inline?: boolean
  /** More buttons after the kind's own (Inicio's «Revisar CLIs» and «Posponer»). */
  extra?: React.ReactNode
  /** No «Ver cambios» button: these are the actions at the foot of the changes panel. */
  hideChanges?: boolean
  /** Called when a review is decided or a delivery marked as seen (closes that panel). */
  onDone?: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const answer = useAnswerItem()
  const permission = usePermissionItem()
  const review = useReviewItem()
  const dismiss = useDismissItem()
  const resume = useResumeItem()
  const switchCli = useSwitchItem()
  const [text, setText] = useState('')
  const [rejecting, setRejecting] = useState(false)
  const [reviewingProposal, setReviewingProposal] = useState<string | null>(null)
  const [reviewingSkill, setReviewingSkill] = useState<string | null>(null)
  const busy =
    answer.isPending ||
    permission.isPending ||
    review.isPending ||
    dismiss.isPending ||
    resume.isPending ||
    switchCli.isPending
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
    <div
      className={cn(
        'flex flex-wrap items-center gap-2',
        !inline && 'border-t border-sep bg-subtle px-4 py-2.5',
      )}
    >
      {(item.kind === 'review' || item.kind === 'delivery') && item.task_id && !hideChanges && (
        <ChangesButton
          target={{ kind: 'task', id: item.task_id }}
          title={t('changes.titleTask', { code: item.task_code ?? '' })}
          totals={item.changes}
          footer={(close) => <RequestActions item={item} hideChanges onDone={close} />}
        />
      )}
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
          <GrowingField
            aria-label={t('inbox.answerPlaceholder')}
            value={text}
            onChange={setText}
            placeholder={t('inbox.answerPlaceholder')}
            containerClassName="w-auto min-w-[220px] flex-1"
            canSubmit={!busy && !!text.trim()}
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
                {
                  onSuccess: () => {
                    toast.success(t('inbox.toast.approved'))
                    onDone?.()
                  },
                  onError,
                },
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
              {
                onSuccess: () => {
                  toast.success(t('inbox.toast.rejected'))
                  onDone?.()
                },
                onError,
              },
            )
          }}
        >
          <GrowingField
            aria-label={t('inbox.reasonPlaceholder')}
            value={text}
            onChange={setText}
            placeholder={t('inbox.reasonPlaceholder')}
            containerClassName="w-auto flex-1"
            canSubmit={!busy && !!text.trim()}
          />
          <Button type="submit" size="sm" disabled={busy || !text.trim()}>
            {t('inbox.reviewReject')}
          </Button>
        </form>
      )}
      {item.kind === 'skill' && item.skill_version_id && (
        <>
          <Button
            size="sm"
            onClick={() => setReviewingSkill(item.skill_version_id ?? null)}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <BookOpenCheck />
            {t('inbox.reviewSkill')}
          </Button>
          <SkillProposalReview versionId={reviewingSkill} onClose={() => setReviewingSkill(null)} />
        </>
      )}
      {item.kind === 'knowledge' && item.knowledge_doc_id && (
        <>
          <Button
            size="sm"
            onClick={() => setReviewingProposal(item.knowledge_doc_id ?? null)}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <BookOpenCheck />
            {t('inbox.reviewProposal')}
          </Button>
          <DocSheet
            docId={reviewingProposal}
            onClose={() => setReviewingProposal(null)}
            onNavigate={setReviewingProposal}
          />
        </>
      )}
      {item.kind === 'proposal' && item.proposal_id && <ReviewProposal id={item.proposal_id} />}
      {item.kind === 'connection' && item.connection_id && (
        <Button
          size="sm"
          className="bg-primary-action text-white hover:bg-primary-action-hover"
          asChild
        >
          <Link to={`/conexiones?conexion=${item.connection_id}`}>
            <LogIn />
            {t('inbox.reconnect')}
          </Link>
        </Button>
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
      {item.kind === 'switch' && item.options.length > 0 && (
        <>
          {/* The backend offers [switch, stay] in that order, named after the accounts. */}
          <Button
            size="sm"
            disabled={busy}
            onClick={() =>
              switchCli.mutate(
                { id: item.id, choice: 'switch' },
                { onSuccess: () => toast.success(t('inbox.toast.switched')), onError },
              )
            }
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <ArrowLeftRight />
            {item.options[0]}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() =>
              switchCli.mutate(
                { id: item.id, choice: 'stay' },
                { onSuccess: () => toast.success(t('inbox.toast.stayed')), onError },
              )
            }
          >
            {item.options[1]}
          </Button>
        </>
      )}
      {item.kind === 'switch' && item.options.length === 0 && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => dismiss.mutate(item.id, { onError })}
        >
          {t('inbox.understood')}
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
      {item.kind === 'account' && (
        <Button
          size="sm"
          className="bg-primary-action text-white hover:bg-primary-action-hover"
          asChild
        >
          {/* The item names the account in `command`: «CLIs y cuentas» opens its login. */}
          <Link to={`/clis?reconectar=${item.command ?? ''}`}>
            <LogIn />
            {t('inbox.reconnect')}
          </Link>
        </Button>
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
          onClick={() => dismiss.mutate(item.id, { onSuccess: () => onDone?.(), onError })}
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
      {extra}
      {item.run_id && (
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          // The run's terminal is on its page (phase 23: the dock has the person's own).
          onClick={() => void navigate(`/ejecuciones/${item.run_id}`)}
        >
          <SquareTerminal />
          {t('inbox.openTerminal')}
        </Button>
      )}
    </div>
  )
}

/** A proposal of the Architect or of an agent (phase 19): reviewed where its agent is. */
function ReviewProposal({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data: proposal } = useProposal(id)
  if (!proposal) return null
  if (!proposal.target_agent_id) {
    if (!proposal.conversation_id) return null
    return (
      <Button
        size="sm"
        className="bg-primary-action text-white hover:bg-primary-action-hover"
        asChild
      >
        <Link to={`/agentes/arquitecto/${proposal.conversation_id}`}>
          <Sparkles />
          {t('inbox.reviewAgentProposal')}
        </Link>
      </Button>
    )
  }
  return (
    <Button
      size="sm"
      className="bg-primary-action text-white hover:bg-primary-action-hover"
      asChild
    >
      <Link to={`/agentes/${proposal.target_agent_id}/resumen`}>
        <Sparkles />
        {t('inbox.reviewAgentProposal')}
      </Link>
    </Button>
  )
}
