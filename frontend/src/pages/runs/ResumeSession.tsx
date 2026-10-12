import { History } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useResumeRun, useRun } from '@/api/runs'
import { useTask } from '@/api/tasks'
import type { Run } from '@/api/types'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

/**
 * «Reanudar sesión» (phase 08): continues the CLI conversation of a run that was cut short.
 * `open`: go to the new run afterwards (from the run's own page).
 */
export function ResumeSessionButton({
  run,
  open = false,
  primary = false,
}: {
  run: Pick<Run, 'id' | 'agent_name'>
  open?: boolean
  primary?: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const resume = useResumeRun()

  async function onResume() {
    try {
      const resumed = await resume.mutateAsync(run.id)
      toast.success(t('runs.resume.done', { name: run.agent_name }))
      if (open) void navigate(`/ejecuciones/${resumed.id}`)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <Button
      size="sm"
      variant={primary ? 'default' : 'outline'}
      title={t('runs.resume.hint')}
      disabled={resume.isPending}
      onClick={() => void onResume()}
      className={primary ? 'bg-primary-action text-white hover:bg-primary-action-hover' : ''}
    >
      <History />
      {t('runs.resume.button')}
    </Button>
  )
}

/** The button for a task whose latest run can be resumed (nothing otherwise). */
export function ResumeTaskSession({ taskId, primary }: { taskId: string; primary?: boolean }) {
  const task = useTask(taskId).data
  const run = useRun(task?.last_run_id ?? undefined).data
  if (!run?.resumable) return null
  return <ResumeSessionButton run={run} primary={primary} />
}
