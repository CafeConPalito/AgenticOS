import {
  AlertTriangle,
  Check,
  CheckCheck,
  FolderGit2,
  ListPlus,
  RotateCcw,
  SquareKanban,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { usePipeline } from '@/api/pipelines'
import { useRun, useRuns } from '@/api/runs'
import {
  type TaskAction,
  isMoving,
  useOpenWorktree,
  useTask,
  useTaskAction,
  useTaskEvents,
} from '@/api/tasks'
import type { Run, Stage, Task } from '@/api/types'
import { AgentAvatar, ProjectChip } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Field, PageContainer } from '@/components/page'
import { TerminalPanel } from '@/components/terminal/TerminalPanel'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { formatDateTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { RunEventsPanel } from '@/pages/runs/RunEventsPanel'
import { RunStatusBadge } from '@/pages/runs/RunStatusBadge'
import { PriorityLabel, TaskStatusBadge } from './TaskBits'

export default function TaskPage() {
  const { taskId = '' } = useParams()
  const { t } = useTranslation()
  const { data: task, isPending, isError } = useTask(taskId)
  if (isPending)
    return (
      <PageContainer>
        <Skeleton aria-busy className="h-24 rounded-lg" />
      </PageContainer>
    )
  if (isError || !task)
    return (
      <PageContainer>
        <EmptyState icon={SquareKanban} title={t('tasks.notFound')} />
      </PageContainer>
    )
  return <TaskDetail task={task} />
}

type Dialogs = 'cancel' | 'complete' | 'reject' | null

function TaskDetail({ task }: { task: Task }) {
  const { t } = useTranslation()
  const act = useTaskAction(task.id)
  const openWorktree = useOpenWorktree()
  const pipeline = usePipeline(task.project_id)
  const stages = pipeline.data?.stages ?? []
  const runId = task.active_run_id ?? task.last_run_id
  const run = useRun(runId ?? undefined).data
  const [dialog, setDialog] = useState<Dialogs>(null)

  async function perform(action: TaskAction) {
    try {
      await act.mutateAsync(action)
      setDialog(null)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const can = {
    enqueue: task.status === 'backlog',
    retry: task.status === 'waiting_human',
    complete: task.status === 'running' || task.status === 'waiting_human',
    review: task.status === 'review',
    cancel: !['done', 'cancelled'].includes(task.status),
  }

  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b px-5 py-3">
        <span className="font-mono text-[12.5px] text-muted-foreground">{task.code}</span>
        <h1 className="min-w-0 truncate text-[17px] font-medium" title={task.title}>
          {task.title}
        </h1>
        <TaskStatusBadge status={task.status} />
        <ProjectChip name={task.project_name} color={task.project_color} />
        {task.agent_name && (
          <span className="inline-flex items-center gap-2 text-[12.5px] text-muted-foreground">
            <AgentAvatar name={task.agent_name} color={task.agent_color ?? '#C9D4E8'} size={18} />
            {task.agent_name}
          </span>
        )}
        <div className="ml-auto flex shrink-0 flex-wrap items-center gap-2">
          {can.review && (
            <>
              <Button
                size="sm"
                onClick={() => void perform({ action: 'review', approve: true })}
                className="bg-primary-action text-white hover:bg-primary-action-hover"
              >
                <Check />
                {t('tasks.actions.approve')}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setDialog('reject')}>
                <X />
                {t('tasks.actions.reject')}
              </Button>
            </>
          )}
          {can.enqueue && (
            <Button variant="outline" size="sm" onClick={() => void perform({ action: 'enqueue' })}>
              <ListPlus />
              {t('tasks.actions.enqueue')}
            </Button>
          )}
          {can.retry && (
            <Button variant="outline" size="sm" onClick={() => void perform({ action: 'retry' })}>
              <RotateCcw />
              {t('tasks.actions.retry')}
            </Button>
          )}
          {can.complete && (
            <Button variant="outline" size="sm" onClick={() => setDialog('complete')}>
              <CheckCheck />
              {t('tasks.actions.complete')}
            </Button>
          )}
          {task.worktree_path && (
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                openWorktree.mutate(task.id, {
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              <FolderGit2 />
              {t('tasks.actions.openWorktree')}
            </Button>
          )}
          {can.cancel && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDialog('cancel')}
              className="border-status-failed/50 text-status-failed hover:bg-status-failed/10 hover:text-status-failed"
            >
              {t('tasks.actions.cancel')}
            </Button>
          )}
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_316px] grid-rows-[minmax(0,1fr)]">
        <TaskSidePanel task={task} stages={stages} />
        <div className="flex min-h-0 flex-col gap-2 p-3.5">
          {run ? (
            <>
              <TerminalPanel key={run.id} run={run} />
              <div className="flex gap-4 px-0.5 font-mono text-[11.5px] text-muted-foreground">
                <span>{t('runs.terminalInfo', { cols: run.cols, rows: run.rows })}</span>
                <span className="truncate">{run.cwd}</span>
                {task.branch && <span className="ml-auto">{task.branch}</span>}
              </div>
            </>
          ) : (
            <div className="grid flex-1 place-items-center rounded-lg border border-dashed text-sm text-muted-foreground">
              {t('tasks.detail.noRun')}
            </div>
          )}
        </div>
        <aside className="flex min-h-0 flex-col overflow-auto border-l p-4">
          {runId && <RunEventsPanel runId={runId} />}
        </aside>
      </div>

      <ConfirmDialog
        open={dialog === 'cancel'}
        onOpenChange={(open) => setDialog(open ? 'cancel' : null)}
        title={t('tasks.actions.cancelTitle', { code: task.code })}
        description={t('tasks.actions.cancelDescription')}
        confirmLabel={t('tasks.actions.cancel')}
        destructive
        onConfirm={() => void perform({ action: 'cancel' })}
      />
      <CompleteDialog
        open={dialog === 'complete'}
        task={task}
        busy={act.isPending}
        onOpenChange={(open) => setDialog(open ? 'complete' : null)}
        onSubmit={(summary) => void perform({ action: 'complete', summary })}
      />
      <RejectDialog
        open={dialog === 'reject'}
        task={task}
        stages={stages}
        busy={act.isPending}
        onOpenChange={(open) => setDialog(open ? 'reject' : null)}
        onSubmit={(reason, target) =>
          void perform({ action: 'review', approve: false, reason, target_stage_id: target })
        }
      />
    </div>
  )
}

function StageStepper({ task, stages }: { task: Task; stages: Stage[] }) {
  const current = stages.findIndex((s) => s.id === task.stage_id)
  return (
    <ol className="flex flex-wrap items-center gap-1.5">
      {stages.map((stage, i) => (
        <li
          key={stage.id}
          aria-current={i === current ? 'step' : undefined}
          className={cn(
            'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[12px]',
            i === current && 'border-status-running bg-status-running/10 font-medium',
            i < current && 'text-muted-foreground',
            i > current && 'text-muted-foreground opacity-70',
          )}
        >
          {stage.agent_name && (
            <AgentAvatar name={stage.agent_name} color={stage.agent_color ?? '#C9D4E8'} size={16} />
          )}
          {stage.name}
        </li>
      ))}
    </ol>
  )
}

function TaskSidePanel({ task, stages }: { task: Task; stages: Stage[] }) {
  const { t } = useTranslation()
  const events = useTaskEvents(task.id, isMoving(task)).data ?? []
  const runs = useRuns({ taskId: task.id }).data ?? []
  const lastSummary = [...events]
    .reverse()
    .find((e) => e.kind === 'stage_completed' || e.kind === 'completed_manually')

  return (
    <aside className="flex min-h-0 flex-col gap-[18px] overflow-auto border-r p-4 text-[13px]">
      {task.status === 'waiting_human' && task.waiting_reason && (
        <section
          role="alert"
          className="rounded-[10px] border border-status-waiting/40 bg-status-waiting/10 px-3.5 py-3"
        >
          <h2 className="mb-1 flex items-center gap-1.5 text-[12.5px] font-medium text-status-waiting">
            <AlertTriangle className="size-3.5" />
            {t('tasks.detail.waiting')}
          </h2>
          <p>{t(`tasks.waiting.${task.waiting_reason}`)}</p>
          {task.waiting_detail && (
            <p className="mt-1 font-mono text-xs break-words text-muted-foreground">
              {task.waiting_detail}
            </p>
          )}
        </section>
      )}
      <section>
        <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">
          {t('tasks.detail.description')}
        </h2>
        <p className="text-[13.5px] whitespace-pre-wrap">
          {task.description || t('tasks.detail.noDescription')}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          <PriorityLabel priority={task.priority} />
          {task.rejections > 0 && (
            <> · {t('tasks.detail.rejections', { count: task.rejections })}</>
          )}
        </p>
      </section>
      {stages.length > 0 && (
        <section>
          <h2 className="mb-2 text-[12.5px] text-muted-foreground">{t('tasks.detail.stages')}</h2>
          <StageStepper task={task} stages={stages} />
        </section>
      )}
      {(task.branch || task.worktree_path) && (
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
          {task.branch && (
            <>
              <dt className="text-muted-foreground">{t('tasks.detail.branch')}</dt>
              <dd className="font-mono break-all">{task.branch}</dd>
            </>
          )}
          {task.worktree_path && (
            <>
              <dt className="text-muted-foreground">{t('tasks.detail.worktree')}</dt>
              <dd className="font-mono break-all">{task.worktree_path}</dd>
            </>
          )}
        </dl>
      )}
      <section>
        <h2 className="mb-2 text-[12.5px] text-muted-foreground">{t('tasks.detail.history')}</h2>
        <ol className="flex flex-col gap-2.5">
          {events
            .filter((e) => e.kind !== 'queued' && e.kind !== 'stage_started')
            .map((event) => (
              <li key={event.id} className="grid grid-cols-[10px_minmax(0,1fr)] gap-2">
                <span
                  aria-hidden
                  className={cn(
                    'mt-1.5 size-2 rounded-full',
                    event.kind === 'rejected' || event.kind === 'review_rejected'
                      ? 'bg-status-failed'
                      : event.kind === 'waiting_human'
                        ? 'bg-status-waiting'
                        : event.kind === 'done'
                          ? 'bg-status-done'
                          : 'bg-status-running',
                  )}
                />
                <div className="min-w-0">
                  <div>
                    <span className="font-medium">{t(`tasks.events.${event.kind}`)}</span>
                    {(event.stage_name || event.agent_name) && (
                      <span className="text-muted-foreground">
                        {' · '}
                        {[event.stage_name, event.agent_name].filter(Boolean).join(' · ')}
                      </span>
                    )}
                  </div>
                  {event.detail && (
                    <p className="line-clamp-3 text-[12.5px] break-words text-muted-foreground">
                      {event.detail}
                    </p>
                  )}
                  <time className="text-[11.5px] text-muted-foreground" dateTime={event.at}>
                    {formatDateTime(event.at)}
                  </time>
                </div>
              </li>
            ))}
        </ol>
      </section>
      <section>
        <h2 className="mb-2 text-[12.5px] text-muted-foreground">{t('tasks.detail.runs')}</h2>
        {runs.length === 0 ? (
          <p className="text-muted-foreground">{t('tasks.detail.noRuns')}</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {runs.map((r: Run) => (
              <li key={r.id}>
                <Link
                  to={`/ejecuciones/${r.id}`}
                  className="flex items-center gap-2 rounded-md px-1 py-0.5 hover:bg-accent"
                >
                  <AgentAvatar name={r.agent_name} color={r.agent_color} size={16} />
                  <span className="truncate">{r.stage_name ?? r.agent_name}</span>
                  <span className="ml-auto">
                    <RunStatusBadge run={r} size="xs" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      {lastSummary?.detail && (
        <section className="rounded-[10px] border bg-subtle px-3.5 py-3">
          <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">
            {t('tasks.detail.lastSummary')}
          </h2>
          <p className="text-[13.5px] whitespace-pre-wrap">{lastSummary.detail}</p>
        </section>
      )}
    </aside>
  )
}

function CompleteDialog({
  open,
  task,
  busy,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  task: Task
  busy: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (summary: string) => void
}) {
  const { t } = useTranslation()
  const [summary, setSummary] = useState('')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t('tasks.actions.completeTitle', { code: task.code })}</DialogTitle>
          <DialogDescription>{t('tasks.actions.completeDescription')}</DialogDescription>
        </DialogHeader>
        <Field label={t('tasks.actions.summary')} htmlFor="complete-summary">
          <Textarea
            id="complete-summary"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder={t('tasks.actions.summaryPlaceholder')}
            className="min-h-[110px]"
          />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!summary.trim() || busy}
            onClick={() => onSubmit(summary.trim())}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('tasks.actions.complete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RejectDialog({
  open,
  task,
  stages,
  busy,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  task: Task
  stages: Stage[]
  busy: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (reason: string, target: string | null) => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const current = stages.find((s) => s.id === task.stage_id)
  const options = stages.filter((s) => current && s.position <= current.position)
  // '' until the user picks one: the default depends on the pipeline, which may load later.
  const [picked, setTarget] = useState('')
  const target = picked || current?.reject_to_stage_id || current?.id || ''
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t('tasks.actions.rejectTitle', { code: task.code })}</DialogTitle>
          <DialogDescription>{t('tasks.actions.rejectDescription')}</DialogDescription>
        </DialogHeader>
        <Field label={t('tasks.actions.reason')} htmlFor="reject-reason">
          <Textarea
            id="reject-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t('tasks.actions.reasonPlaceholder')}
            className="min-h-[110px]"
          />
        </Field>
        {options.length > 0 && (
          <Field label={t('tasks.actions.target')} htmlFor="reject-target">
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger id="reject-target" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {options.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!reason.trim() || busy}
            onClick={() => onSubmit(reason.trim(), target || null)}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('tasks.actions.reject')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
