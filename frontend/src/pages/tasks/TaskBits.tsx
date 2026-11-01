// Small pieces shared by the board, the project's tasks tab and the task page.
import { Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { Priority, Task, TaskStatus } from '@/api/types'
import {
  AgentAvatar,
  ProjectChip,
  StatusBadge,
  type StatusTone,
} from '@/components/agentic/primitives'
import { cn } from '@/lib/utils'
import { NEUTRAL_COLOR } from '@/theme/palettes'
import { WorkModeTag } from './WorkModeSection'

export const TASK_TONE: Record<TaskStatus, StatusTone> = {
  backlog: 'cancelled',
  queued: 'queued',
  running: 'running',
  waiting_human: 'waiting',
  review: 'review',
  done: 'done',
  cancelled: 'cancelled',
}

export function TaskStatusBadge({
  status,
  size = 'md',
}: {
  status: TaskStatus
  size?: 'md' | 'sm' | 'xs'
}) {
  const { t } = useTranslation()
  return <StatusBadge tone={TASK_TONE[status]} label={t(`tasks.status.${status}`)} size={size} />
}

const PRIORITY_CLASS: Record<Priority, string> = {
  high: 'text-status-waiting',
  normal: 'text-muted-foreground',
  low: 'text-muted-foreground',
}

export function PriorityLabel({ priority }: { priority: Priority }) {
  const { t } = useTranslation()
  return <span className={PRIORITY_CLASS[priority]}>{t(`tasks.priority.${priority}`)}</span>
}

export function TaskAgent({ task, size = 18 }: { task: Task; size?: number }) {
  const { t } = useTranslation()
  if (!task.agent_name) return <span className="text-muted-foreground">{t('tasks.noAgent')}</span>
  return (
    <AgentAvatar
      name={task.agent_name}
      agentId={task.agent_id}
      color={task.agent_color ?? NEUTRAL_COLOR}
      size={size}
      label={task.agent_name}
      withTooltip
    />
  )
}

/** Board card (design 07a): project, stage, code, title, agent and priority. */
export function TaskCard({
  task,
  showStatus = false,
  className,
}: {
  task: Task
  showStatus?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <Link
      to={`/tablero/tareas/${task.id}`}
      aria-label={t('tasks.open', { code: task.code, title: task.title })}
      className={cn(
        'block rounded-[10px] border bg-card px-3 py-2.5 transition-colors hover:border-ring/60',
        task.status === 'running' && 'border-t-2 border-t-status-running',
        className,
      )}
    >
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <ProjectChip
          name={task.project_name}
          color={task.project_color}
          projectId={task.project_id}
        />
        {task.status === 'done' && task.exit_stage_name ? (
          // Phase 24: an exit ended it before the last stage.
          <span className="truncate">
            {t('tasks.exit.endedAt', { stage: task.exit_stage_name })}
          </span>
        ) : (
          task.stage_name && <span className="truncate">{task.stage_name}</span>
        )}
        {task.lane_name && (
          <span className="truncate rounded-full border px-1.5 text-[10.5px]">
            {t('tasks.lanes.laneTag', { name: task.lane_name })}
          </span>
        )}
        {task.phase === 'forked' && (
          <span className="rounded-full border px-1.5 text-[10.5px]">
            {t('tasks.lanes.lanesTag', { count: task.lanes.length })}
          </span>
        )}
        <WorkModeTag task={task} />
        <span className="ml-auto font-mono">{task.code}</span>
      </div>
      <div className="mt-1.5 line-clamp-2 text-[13.5px] font-medium">{task.title}</div>
      <div className="mt-2 flex items-center gap-2 text-[11.5px]">
        <TaskAgent task={task} />
        <PriorityLabel priority={task.priority} />
        {task.blocked && (
          <span className="inline-flex items-center gap-1 text-status-waiting">
            <Lock className="size-3" />
            {t(`tasks.blocked.${task.blocked}`, { account: task.blocked_by ?? '' })}
          </span>
        )}
        {showStatus && (
          <span className="ml-auto">
            <TaskStatusBadge status={task.status} size="xs" />
          </span>
        )}
      </div>
    </Link>
  )
}
