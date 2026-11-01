import { FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useChangeWorkMode } from '@/api/tasks'
import type { Task } from '@/api/types'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

/** Phase 24: why the mode of a task cannot be changed now (null: it can). */
function lockedReason(task: Task): 'lane' | 'forked' | 'finished' | 'running' | null {
  if (task.lane_of_id) return 'lane'
  if (task.phase === 'forked' || task.lanes.length > 0) return 'forked'
  if (task.status === 'done' || task.status === 'cancelled') return 'finished'
  if (task.status === 'running') return 'running'
  return null
}

/**
 * How the task is worked (phase 24, ADR 0030): with SDD (its spec folder) or without, as its
 * requirements stage chose, and the person's change, which sends it back to its first stage.
 */
export function WorkModeSection({ task }: { task: Task }) {
  const { t } = useTranslation()
  const change = useChangeWorkMode(task.id)
  if (!task.work_mode) return null
  const other = task.work_mode === 'sdd' ? 'direct' : 'sdd'
  const locked = lockedReason(task)

  async function onChange() {
    try {
      await change.mutateAsync(other)
      toast.success(t('tasks.workMode.changed'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <section aria-labelledby="work-mode-title" className="grid gap-1.5">
      <h2
        id="work-mode-title"
        className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground"
      >
        <FileText className="size-3.5" />
        {t('tasks.workMode.title')}
      </h2>
      <p className="font-medium">{t(`tasks.workMode.${task.work_mode}`)}</p>
      {task.work_mode_reason && (
        <p className="text-xs text-muted-foreground">{task.work_mode_reason}</p>
      )}
      {task.spec_path && (
        <p className="text-xs">
          {t('tasks.workMode.spec')} <code className="font-mono">{task.spec_path}</code>
        </p>
      )}
      <div>
        <Button
          size="sm"
          variant="outline"
          disabled={locked !== null || change.isPending}
          title={locked ? t(`tasks.workMode.locked.${locked}`) : t('tasks.workMode.changeHelp')}
          onClick={() => void onChange()}
        >
          {t(`tasks.workMode.changeTo.${other}`)}
        </Button>
      </div>
    </section>
  )
}

/** The small tag of the mode on a task card. */
export function WorkModeTag({ task }: { task: Task }) {
  const { t } = useTranslation()
  if (!task.work_mode) return null
  return (
    <span className="rounded-full border px-1.5 text-[10.5px]">
      {t(`tasks.workMode.tag.${task.work_mode}`)}
    </span>
  )
}
