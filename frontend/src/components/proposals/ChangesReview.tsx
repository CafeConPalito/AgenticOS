import { AlertTriangle, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import {
  type FieldChange,
  type Proposal,
  useApproveProposal,
  usePendingProposals,
  useRejectProposal,
} from '@/api/architect'
import type { Agent } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { fieldLabel } from '@/pages/architect/ArchitectChat'

/** An active agent with changes proposed by the Architect (phase 19, block 8): it keeps working
 * as it is until the person applies them, all or field by field. */
export function ChangesBanner({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const { data } = usePendingProposals(agent.id)
  const reject = useRejectProposal()
  const [reviewing, setReviewing] = useState<Proposal | null>(null)
  const proposal = data?.find((p) => p.kind === 'agent_changes')
  if (!proposal) return null
  return (
    <div
      role="region"
      aria-label={t('proposals.changesTitle')}
      className="flex items-center gap-3 border-b px-6 py-3"
      style={{
        background: 'color-mix(in oklch, var(--status-review) 10%, transparent)',
        borderColor: 'color-mix(in oklch, var(--status-review) 30%, transparent)',
      }}
    >
      <Sparkles className="size-5 shrink-0 text-status-review" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{t('proposals.changesTitle')}</p>
        <p className="text-[12.5px] text-muted-foreground">
          {t('proposals.changesHelp', { count: proposal.changes.length })}
          {proposal.conversation_id && (
            <>
              {' '}
              <Link to={`/agentes/arquitecto/${proposal.conversation_id}`} className="underline">
                {t('proposals.openConversation')}
              </Link>
            </>
          )}
        </p>
      </div>
      <Button
        type="button"
        variant="outline"
        disabled={reject.isPending}
        onClick={() =>
          reject.mutate(
            { id: proposal.id, archive: false },
            {
              onSuccess: () => toast.success(t('proposals.changesRejected')),
              onError: (error) => toast.error(errorMessage(error)),
            },
          )
        }
      >
        {t('proposals.reject')}
      </Button>
      <Button
        type="button"
        onClick={() => setReviewing(proposal)}
        className="bg-primary-action text-white hover:bg-primary-action-hover"
      >
        {t('proposals.review')}
      </Button>
      <ChangesReview proposal={reviewing} onClose={() => setReviewing(null)} />
    </div>
  )
}

/** The fields of a proposal of changes: before and after (the instructions as a diff), which to
 * apply, and for a field changed by hand since the proposal, which value stays. */
export function ChangesReview({
  proposal,
  onClose,
}: {
  proposal: Proposal | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const approve = useApproveProposal()
  const [skipped, setSkipped] = useState<string[]>([])
  const [choices, setChoices] = useState<Record<string, 'proposed' | 'current'>>({})
  const [skippedSkills, setSkippedSkills] = useState<string[]>([])
  if (!proposal) return null
  const chosen = proposal.changes.filter((c) => !skipped.includes(c.field))
  const unsettled = chosen.filter((c) => c.conflict && !choices[c.field])

  async function apply() {
    try {
      const done = await approve.mutateAsync({
        id: proposal!.id,
        fields: chosen.map((c) => c.field),
        choices,
        skip_skills: skippedSkills,
      })
      toast.success(t('proposals.changesApplied', { count: done.proposal.applied_fields.length }))
      for (const note of done.notes) toast.warning(note)
      onClose()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100vh-48px)] overflow-y-auto sm:max-w-[760px]">
        <DialogHeader>
          <DialogTitle>{t('proposals.reviewTitle')}</DialogTitle>
          <DialogDescription>{t('proposals.reviewHelp')}</DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-3">
          {proposal.changes.map((change) => (
            <ChangeRow
              key={change.field}
              change={change}
              on={!skipped.includes(change.field)}
              onToggle={(on) =>
                setSkipped((s) => (on ? s.filter((x) => x !== change.field) : [...s, change.field]))
              }
              choice={choices[change.field]}
              onChoice={(value) => setChoices((c) => ({ ...c, [change.field]: value }))}
            />
          ))}
        </ul>
        {proposal.new_skills.length > 0 && (
          <section>
            <h3 className="mb-1 text-[13px] font-medium">{t('proposals.newSkills')}</h3>
            <ul className="space-y-1.5">
              {proposal.new_skills.map((skill) => (
                <li key={skill.id} className="flex items-center gap-2">
                  <Switch
                    id={`new-skill-${skill.id}`}
                    checked={!skippedSkills.includes(skill.id)}
                    onCheckedChange={(on) =>
                      setSkippedSkills((s) =>
                        on ? s.filter((x) => x !== skill.id) : [...s, skill.id],
                      )
                    }
                  />
                  <Label htmlFor={`new-skill-${skill.id}`} className="font-mono text-[12.5px]">
                    {skill.name}
                  </Label>
                </li>
              ))}
            </ul>
          </section>
        )}
        <DialogFooter>
          {unsettled.length > 0 && (
            <p className="mr-auto self-center text-[12.5px] text-status-waiting">
              {t('proposals.settleConflicts')}
            </p>
          )}
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            disabled={chosen.length === 0 || unsettled.length > 0 || approve.isPending}
            onClick={() => void apply()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('proposals.applySelected', { count: chosen.length })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ChangeRow({
  change,
  on,
  onToggle,
  choice,
  onChoice,
}: {
  change: FieldChange
  on: boolean
  onToggle: (on: boolean) => void
  choice: 'proposed' | 'current' | undefined
  onChoice: (value: 'proposed' | 'current') => void
}) {
  const { t } = useTranslation()
  const label = fieldLabel(t, change.field)
  return (
    <li className={cn('rounded-lg border border-sep p-3', !on && 'opacity-60')}>
      <div className="flex items-center gap-2">
        <Switch id={`field-${change.field}`} checked={on} onCheckedChange={onToggle} />
        <Label htmlFor={`field-${change.field}`} className="font-medium capitalize">
          {label}
        </Label>
        {change.conflict && (
          <span className="ml-auto flex items-center gap-1 text-[12px] text-status-waiting">
            <AlertTriangle className="size-3.5" aria-hidden />
            {t('proposals.conflict')}
          </span>
        )}
      </div>
      {change.field === 'instructions' ? (
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-2 font-mono text-[12px] whitespace-pre-wrap">
          {change.diff.split('\n').map((line, i) => (
            <span
              key={i}
              className={cn(
                'block',
                line.startsWith('+') && !line.startsWith('+++') && 'text-status-done',
                line.startsWith('-') && !line.startsWith('---') && 'text-status-failed',
              )}
            >
              {line}
            </span>
          ))}
        </pre>
      ) : (
        <p className="mt-2 text-[13px]">
          <span className="text-muted-foreground line-through">{show(t, change.before)}</span>
          {' → '}
          <span>{show(t, change.after)}</span>
        </p>
      )}
      {change.conflict && on && (
        <div className="mt-2">
          <p className="text-[12.5px] text-muted-foreground">
            {t('proposals.conflictHelp', { value: show(t, change.current) })}
          </p>
          <RadioGroup
            value={choice ?? ''}
            onValueChange={(value) => onChoice(value as 'proposed' | 'current')}
            className="mt-1 flex gap-4"
            aria-label={t('proposals.conflictChoice', { field: label })}
          >
            <Label className="flex items-center gap-1.5 font-normal">
              <RadioGroupItem value="proposed" />
              {t('proposals.keepProposed')}
            </Label>
            <Label className="flex items-center gap-1.5 font-normal">
              <RadioGroupItem value="current" />
              {t('proposals.keepCurrent')}
            </Label>
          </RadioGroup>
        </div>
      )}
    </li>
  )
}

/** A value of the sheet in a line: names of the lists, yes/no, or the text. */
function show(
  t: (key: 'common.yes' | 'common.no' | 'architect.none') => string,
  value: unknown,
): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return t(value ? 'common.yes' : 'common.no')
  if (Array.isArray(value)) {
    if (value.length === 0) return t('architect.none')
    return value
      .map((item) =>
        typeof item === 'object' && item
          ? String(
              (item as Record<string, unknown>).name ??
                (item as Record<string, unknown>).title ??
                JSON.stringify(item),
            ) +
            ((item as Record<string, unknown>).mode
              ? ` (${String((item as Record<string, unknown>).mode)})`
              : '')
          : String(item),
      )
      .join(', ')
  }
  return String(value)
}
