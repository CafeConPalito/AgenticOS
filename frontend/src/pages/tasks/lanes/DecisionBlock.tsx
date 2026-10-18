import { GitFork } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useDecide, useTaskDecisions } from '@/api/tasks'
import type { Pipeline, Task } from '@/api/types'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

/**
 * The branches of a fork: where the person picks them (nobody could, or a proposal waits to be
 * confirmed) and, once decided, who chose what and why.
 */
export function DecisionBlock({ task, pipeline }: { task: Task; pipeline: Pipeline }) {
  const { t } = useTranslation()
  const decisions = useTaskDecisions(task.id).data ?? []
  const decide = useDecide(task.id)
  const fork = task.stage_id
  const links = pipeline.links
    .filter((l) => l.from_stage_id === fork)
    .sort((a, b) => a.position - b.position)
  const proposal = decisions.find((d) => d.proposed && d.fork_stage_id === fork)
  const choosing =
    links.length > 1 &&
    ((task.status === 'waiting_human' && task.waiting_reason === 'choose_branch') || proposal)
  const past = decisions.filter((d) => !d.proposed)
  const [picked, setPicked] = useState<string[] | null>(null)
  const chosen = picked ?? proposal?.chosen ?? []

  if (!choosing && past.length === 0) return null

  async function onTake() {
    try {
      await decide.mutateAsync(chosen)
      setPicked(null)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const name = (linkId: string) => pipeline.links.find((l) => l.id === linkId)?.name ?? linkId

  return (
    <section aria-labelledby="decision-title" className="flex flex-col gap-2">
      <h2
        id="decision-title"
        className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground"
      >
        <GitFork className="size-3.5" />
        {t('tasks.lanes.decisionTitle')}
      </h2>
      {choosing && (
        <fieldset className="grid gap-2 rounded-[10px] border border-status-waiting/40 bg-status-waiting/10 px-3 py-2.5">
          <legend className="px-1 text-[12.5px] font-medium">
            {proposal ? t('tasks.lanes.confirm') : t('tasks.lanes.choose')}
          </legend>
          {links.map((link) => (
            <label key={link.id} className="flex items-start gap-2 text-[13px]">
              <input
                type="checkbox"
                className="mt-1"
                checked={chosen.includes(link.id)}
                onChange={(e) =>
                  setPicked(
                    e.target.checked ? [...chosen, link.id] : chosen.filter((x) => x !== link.id),
                  )
                }
              />
              <span>
                {link.name}
                {link.always && (
                  <span className="text-muted-foreground"> · {t('tasks.lanes.always')}</span>
                )}
                <span className="block text-xs text-muted-foreground">
                  {proposal?.reasons[link.id] || link.condition}
                </span>
              </span>
            </label>
          ))}
          <div>
            <Button
              size="sm"
              disabled={chosen.length === 0 || decide.isPending}
              onClick={() => void onTake()}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {proposal && picked === null ? t('tasks.lanes.accept') : t('tasks.lanes.take')}
            </Button>
          </div>
        </fieldset>
      )}
      {past.length > 0 && (
        <ul aria-label={t('tasks.lanes.decisions')} className="grid gap-2 text-[13px]">
          {past.map((d) => (
            <li key={d.id} className="rounded-[10px] border bg-subtle px-3 py-2">
              <p className="text-xs text-muted-foreground">{t(`tasks.lanes.by.${d.decided_by}`)}</p>
              <ul className="mt-1 grid gap-0.5">
                {pipeline.links
                  .filter((l) => l.from_stage_id === d.fork_stage_id)
                  .sort((a, b) => a.position - b.position)
                  .map((l) => (
                    <li key={l.id}>
                      <span aria-hidden>{d.chosen.includes(l.id) ? '✓' : '✗'}</span>{' '}
                      <span className="sr-only">
                        {d.chosen.includes(l.id)
                          ? t('tasks.lanes.taken')
                          : t('tasks.lanes.notTaken')}
                      </span>
                      {name(l.id)}
                      {d.reasons[l.id] && (
                        <span className="text-muted-foreground"> — {d.reasons[l.id]}</span>
                      )}
                    </li>
                  ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
