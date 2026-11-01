import { Flag, GitFork } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useContinueTask, useDecide, useTaskDecisions } from '@/api/tasks'
import type { Pipeline, Task } from '@/api/types'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

/** Phase 24: «Terminar aquí» in a decision's `chosen`, next to the link ids. */
export const EXIT = 'exit'

/**
 * The decisions of a task: the branches of a fork and, at a stage with an exit (phase 24),
 * whether the task ends there. Where the person picks (nobody could, or a proposal waits to be
 * confirmed), who chose what and why once decided, and «Seguir con el pipeline» for a task
 * that ended at an exit.
 */
export function DecisionBlock({ task, pipeline }: { task: Task; pipeline: Pipeline }) {
  const { t } = useTranslation()
  const decisions = useTaskDecisions(task.id).data ?? []
  const decide = useDecide(task.id)
  const goOn = useContinueTask(task.id)
  const at = task.stage_id
  const stage = pipeline.stages.find((s) => s.id === at)
  const exitCondition = stage?.exit_condition ?? null
  const links = pipeline.links
    .filter((l) => l.from_stage_id === at)
    .sort((a, b) => a.position - b.position)
  const fork = links.length > 1
  const proposal = decisions.find((d) => d.proposed && d.fork_stage_id === at)
  const choosing =
    (fork || exitCondition !== null) &&
    ((task.status === 'waiting_human' && task.waiting_reason === 'choose_branch') || proposal)
  const ended = task.status === 'done' && task.exit_stage_id !== null
  const past = decisions.filter((d) => !d.proposed)
  const [picked, setPicked] = useState<string[] | null>(null)
  const chosen = picked ?? proposal?.chosen ?? []

  if (!choosing && !ended && past.length === 0) return null

  async function onTake() {
    try {
      await decide.mutateAsync(chosen)
      setPicked(null)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onContinue() {
    try {
      await goOn.mutateAsync()
      toast.success(t('tasks.exit.continued'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const stageName = (id: string) => pipeline.stages.find((s) => s.id === id)?.name ?? ''
  const name = (linkId: string) => pipeline.links.find((l) => l.id === linkId)?.name ?? linkId
  // Ending is exclusive: picking it drops the branches, picking a branch drops it.
  const toggle = (id: string, on: boolean) => {
    if (id === EXIT) setPicked(on ? [EXIT] : [])
    else if (!fork) setPicked(on ? [id] : [])
    else setPicked(on ? [...chosen.filter((x) => x !== EXIT), id] : chosen.filter((x) => x !== id))
  }

  return (
    <section aria-labelledby="decision-title" className="flex flex-col gap-2">
      <h2
        id="decision-title"
        className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground"
      >
        <GitFork className="size-3.5" />
        {t('tasks.lanes.decisionTitle')}
      </h2>
      {ended && (
        <div className="grid gap-2 rounded-[10px] border bg-subtle px-3 py-2.5 text-[13px]">
          <p className="flex items-center gap-1.5 font-medium">
            <Flag className="size-3.5" />
            {t('tasks.exit.endedAt', { stage: task.exit_stage_name ?? '' })}
          </p>
          <div>
            <Button
              size="sm"
              variant="outline"
              disabled={goOn.isPending}
              onClick={() => void onContinue()}
            >
              {t('tasks.exit.continue')}
            </Button>
          </div>
        </div>
      )}
      {choosing && (
        <fieldset className="grid gap-2 rounded-[10px] border border-status-waiting/40 bg-status-waiting/10 px-3 py-2.5">
          <legend className="px-1 text-[12.5px] font-medium">
            {proposal
              ? t(fork ? 'tasks.lanes.confirm' : 'tasks.exit.confirm')
              : t(fork ? 'tasks.lanes.choose' : 'tasks.exit.choose')}
          </legend>
          {exitCondition !== null && (
            <label className="flex items-start gap-2 text-[13px]">
              <input
                type="checkbox"
                className="mt-1"
                checked={chosen.includes(EXIT)}
                onChange={(e) => toggle(EXIT, e.target.checked)}
              />
              <span>
                {t('tasks.exit.option')}
                <span className="block text-xs text-muted-foreground">
                  {proposal?.reasons[EXIT] || exitCondition}
                </span>
              </span>
            </label>
          )}
          {links.map((link) => (
            <label key={link.id} className="flex items-start gap-2 text-[13px]">
              <input
                type="checkbox"
                className="mt-1"
                checked={chosen.includes(link.id)}
                onChange={(e) => toggle(link.id, e.target.checked)}
              />
              <span>
                {fork ? link.name : t('tasks.exit.goOn', { stage: stageName(link.to_stage_id) })}
                {fork && (link.always || !link.condition.trim()) && (
                  <span className="text-muted-foreground"> · {t('tasks.lanes.always')}</span>
                )}
                {fork && (
                  <span className="block text-xs text-muted-foreground">
                    {proposal?.reasons[link.id] || link.condition}
                  </span>
                )}
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
              {proposal && picked === null
                ? t('tasks.lanes.accept')
                : chosen.includes(EXIT)
                  ? t('tasks.exit.end')
                  : fork
                    ? t('tasks.lanes.take')
                    : t('tasks.exit.goOnButton')}
            </Button>
          </div>
        </fieldset>
      )}
      {past.length > 0 && (
        <ul aria-label={t('tasks.lanes.decisions')} className="grid gap-2 text-[13px]">
          {past.map((d) => {
            const at = pipeline.stages.find((s) => s.id === d.fork_stage_id)
            const outs = pipeline.links
              .filter((l) => l.from_stage_id === d.fork_stage_id)
              .sort((a, b) => a.position - b.position)
            const rows = [
              ...(at?.exit_condition != null || d.chosen.includes(EXIT)
                ? [{ id: EXIT, label: t('tasks.exit.option') }]
                : []),
              ...(outs.length > 1 && !d.chosen.includes(EXIT)
                ? outs.map((l) => ({ id: l.id, label: name(l.id) }))
                : []),
            ]
            return (
              <li key={d.id} className="rounded-[10px] border bg-subtle px-3 py-2">
                <p className="text-xs text-muted-foreground">
                  <span>{t(`tasks.lanes.by.${d.decided_by}`)}</span>
                  {at && <span> · {at.name}</span>}
                </p>
                <ul className="mt-1 grid gap-0.5">
                  {rows.map((row) => (
                    <li key={row.id}>
                      <span aria-hidden>{d.chosen.includes(row.id) ? '✓' : '✗'}</span>{' '}
                      <span className="sr-only">
                        {d.chosen.includes(row.id)
                          ? t('tasks.lanes.taken')
                          : t('tasks.lanes.notTaken')}
                      </span>
                      {row.label}
                      {d.reasons[row.id] && (
                        <span className="text-muted-foreground"> — {d.reasons[row.id]}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
