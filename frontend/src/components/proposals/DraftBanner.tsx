import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useApproveProposal, useProposal, useRejectProposal } from '@/api/architect'
import type { Agent } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'

/** A draft agent proposed by the Architect or by another agent (phase 19, design §3): it gets
 * no tasks until the person approves it here (its skills and documents come with it). */
export function DraftBanner({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const { data: proposal } = useProposal(agent.proposal_id)
  const approve = useApproveProposal()
  const reject = useRejectProposal()
  const [approving, setApproving] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [archive, setArchive] = useState(false)
  const [skipped, setSkipped] = useState<string[]>([])

  if (!proposal || proposal.status !== 'pending') return null
  const byAgent = proposal.origin === 'agent'

  async function onApprove() {
    try {
      const done = await approve.mutateAsync({ id: proposal!.id, skip_skills: skipped })
      toast.success(t('proposals.approved', { name: agent.name }))
      for (const note of done.notes) toast.warning(note)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onReject() {
    try {
      await reject.mutateAsync({ id: proposal!.id, archive })
      toast.success(t(archive ? 'proposals.archived' : 'proposals.rejected', { name: agent.name }))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div
      role="region"
      aria-label={t('proposals.draftTitle')}
      className="flex items-center gap-3 border-b px-6 py-3"
      style={{
        background: 'color-mix(in oklch, var(--status-review) 10%, transparent)',
        borderColor: 'color-mix(in oklch, var(--status-review) 30%, transparent)',
      }}
    >
      <Sparkles className="size-5 shrink-0 text-status-review" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {t(byAgent ? 'proposals.draftByAgent' : 'proposals.draftTitle')}
        </p>
        <p className="text-[12.5px] text-muted-foreground">
          {proposal.reason ? `${proposal.reason} · ` : ''}
          {t('proposals.draftHelp')}
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
        onClick={() => setRejecting(true)}
        disabled={reject.isPending}
      >
        {t('proposals.reject')}
      </Button>
      <Button
        type="button"
        onClick={() => (proposal.new_skills.length > 0 ? setApproving(true) : void onApprove())}
        disabled={approve.isPending}
        className="bg-primary-action text-white hover:bg-primary-action-hover"
      >
        {t('proposals.approveAgent')}
      </Button>

      <ConfirmDialog
        open={approving}
        onOpenChange={setApproving}
        title={t('proposals.approveTitle', { name: agent.name })}
        description={t('proposals.approveSkills')}
        confirmLabel={t('proposals.approveAgent')}
        onConfirm={() => void onApprove()}
      >
        <ul className="space-y-2">
          {proposal.new_skills.map((skill) => {
            const kept = !skipped.includes(skill.id)
            return (
              <li key={skill.id} className="flex items-start gap-2">
                <Switch
                  id={`skill-${skill.id}`}
                  checked={kept}
                  onCheckedChange={(on) =>
                    setSkipped((current) =>
                      on ? current.filter((x) => x !== skill.id) : [...current, skill.id],
                    )
                  }
                />
                <Label htmlFor={`skill-${skill.id}`} className="flex flex-col items-start gap-0.5">
                  <span className="font-mono text-[12.5px]">{skill.name}</span>
                  <span className="text-[12px] font-normal text-muted-foreground">
                    {skill.description}
                  </span>
                </Label>
              </li>
            )
          })}
        </ul>
      </ConfirmDialog>

      <ConfirmDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title={t('proposals.rejectTitle', { name: agent.name })}
        description={t('proposals.rejectHelp')}
        confirmLabel={t('proposals.reject')}
        destructive
        onConfirm={() => void onReject()}
      >
        <div className="flex items-center gap-2">
          <Switch id="archive-draft" checked={archive} onCheckedChange={setArchive} />
          <Label htmlFor="archive-draft">{t('proposals.archive')}</Label>
        </div>
      </ConfirmDialog>
    </div>
  )
}
