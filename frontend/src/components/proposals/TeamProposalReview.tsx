import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type Proposal, useApproveProposal, useRejectProposal } from '@/api/architect'
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

/** A proposal of a team or of changes to a team or a pipeline (phase 19, block 10): the new
 * agents (each can be left out), the reused ones and what the pipeline gains, loses or changes. */
export function TeamProposalReview({
  proposal,
  onClose,
}: {
  proposal: Proposal
  onClose: () => void
}) {
  const { t } = useTranslation()
  const approve = useApproveProposal()
  const reject = useRejectProposal()
  const [skipped, setSkipped] = useState<string[]>([])
  const [choice, setChoice] = useState<'proposed' | 'current' | undefined>()
  const review = proposal.team
  if (!review) return null
  const pipeline = review.pipeline
  const conflict = Boolean(pipeline?.conflict)
  const unsettled = conflict && !choice

  async function apply() {
    try {
      const done = await approve.mutateAsync({
        id: proposal.id,
        skip_agents: skipped,
        choices: conflict && choice ? { pipeline: choice } : {},
      })
      toast.success(t('proposals.teamApplied'))
      for (const note of done.notes) toast.warning(note)
      onClose()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function discard() {
    try {
      await reject.mutateAsync({ id: proposal.id, archive: false })
      toast.success(t('proposals.teamRejected'))
      onClose()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100vh-48px)] overflow-y-auto sm:max-w-[680px]">
        <DialogHeader>
          <DialogTitle>
            {review.team.name
              ? t('proposals.teamTitle', { name: review.team.name })
              : t('proposals.pipelineTitle')}
          </DialogTitle>
          <DialogDescription>{t('proposals.teamHelp')}</DialogDescription>
        </DialogHeader>

        {review.new_agents.length > 0 && (
          <section>
            <h3 className="mb-1 text-[13px] font-medium">{t('proposals.newAgents')}</h3>
            <ul className="space-y-1.5">
              {review.new_agents.map((agent) => (
                <li key={agent.ref} className="flex items-center gap-2">
                  <Switch
                    id={`agent-${agent.ref}`}
                    checked={!skipped.includes(agent.ref)}
                    onCheckedChange={(on) =>
                      setSkipped((s) => (on ? s.filter((x) => x !== agent.ref) : [...s, agent.ref]))
                    }
                  />
                  <Label htmlFor={`agent-${agent.ref}`} className="font-normal">
                    <span className="font-medium">{agent.name}</span>
                    <span className="text-muted-foreground"> · {agent.role}</span>
                  </Label>
                </li>
              ))}
            </ul>
          </section>
        )}
        {review.existing_agents.length > 0 && (
          <section>
            <h3 className="mb-1 text-[13px] font-medium">{t('proposals.existingAgents')}</h3>
            <p className="text-[13px] text-muted-foreground">
              {review.existing_agents.map((a) => a.name).join(', ')}
            </p>
          </section>
        )}
        {pipeline && (
          <section>
            <h3 className="mb-1 text-[13px] font-medium">
              {t('proposals.pipelineOf', { project: pipeline.project_name })}
            </h3>
            <ol className="list-decimal space-y-0.5 pl-5 text-[13px]">
              {pipeline.stages.map((stage) => (
                <li key={stage.name}>
                  <span className="font-medium">{stage.name}</span>
                  <span className="text-muted-foreground"> · {stage.agent}</span>
                </li>
              ))}
            </ol>
            <ul className="mt-2 space-y-0.5 text-[12.5px]">
              {pipeline.added.length > 0 && (
                <li className="text-status-done">
                  {t('proposals.stagesAdded', { names: pipeline.added.join(', ') })}
                </li>
              )}
              {pipeline.removed.length > 0 && (
                <li className="text-status-failed">
                  {t('proposals.stagesRemoved', { names: pipeline.removed.join(', ') })}
                </li>
              )}
              {pipeline.changed.length > 0 && (
                <li className="text-status-review">
                  {t('proposals.stagesChanged', { names: pipeline.changed.join(', ') })}
                </li>
              )}
              {pipeline.links_changed && <li>{t('proposals.linksChanged')}</li>}
            </ul>
            {conflict && (
              <div className="mt-2 rounded-lg border border-sep p-3">
                <p className="flex items-center gap-1.5 text-[12.5px] text-status-waiting">
                  <AlertTriangle className="size-3.5" aria-hidden />
                  {t('proposals.pipelineConflict')}
                </p>
                <RadioGroup
                  value={choice ?? ''}
                  onValueChange={(v) => setChoice(v as 'proposed' | 'current')}
                  className="mt-1 flex gap-4"
                  aria-label={t('proposals.pipelineConflictChoice')}
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
          </section>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={reject.isPending}
            onClick={() => void discard()}
          >
            {t('proposals.reject')}
          </Button>
          <Button
            type="button"
            disabled={unsettled || approve.isPending}
            onClick={() => void apply()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('proposals.approveTeam')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
