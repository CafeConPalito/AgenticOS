import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  horizontalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  ChevronLeft,
  ChevronRight,
  GripVertical,
  Pause,
  Play,
  Plus,
  SquareKanban,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { useReorderQueue, useScheduler, useSetSchedulerPaused, useTasks } from '@/api/tasks'
import type { Agent, Task, TaskStatus } from '@/api/types'
import { AgentAvatar, CliTag } from '@/components/agentic/primitives'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'
import { useDialogs } from '@/stores/dialogs'
import { cn } from '@/lib/utils'
import { PriorityLabel, TASK_TONE, TaskCard, TaskStatusBadge } from '@/pages/tasks/TaskBits'

type View = 'status' | 'stage' | 'queues'
const VIEWS: View[] = ['status', 'stage', 'queues']
const STATUS_COLUMNS: TaskStatus[] = [
  'backlog',
  'queued',
  'running',
  'waiting_human',
  'review',
  'done',
]
const PRIORITY_RANK = { high: 0, normal: 1, low: 2 } as const

/** A queue as the scheduler reads it: priority first, then position. */
export function queueOrder(tasks: Task[]): Task[] {
  return [...tasks].sort(
    (a, b) =>
      PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || a.queue_position - b.queue_position,
  )
}

export default function BoardPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const view = (VIEWS as string[]).includes(params.get('vista') ?? '')
    ? (params.get('vista') as View)
    : 'status'
  const [projectId, setProjectId] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)
  const openNewTask = useDialogs((s) => s.openNewTask)
  // The lanes of forked tasks come too: «Por etapa» and the queues show them as tasks.
  const tasks = useTasks({ lanes: true })
  const projects = useProjects().data ?? []
  const agents = (useAgents().data ?? []).filter((a) => a.status !== 'draft')

  const visible = useMemo(
    () =>
      (tasks.data ?? []).filter(
        (task) =>
          task.status !== 'cancelled' &&
          (!projectId || task.project_id === projectId) &&
          (!agentId || task.agent_id === agentId),
      ),
    [tasks.data, projectId, agentId],
  )

  if (tasks.isSuccess && tasks.data.length === 0)
    return (
      <div className="p-6">
        <EmptyState
          icon={SquareKanban}
          title={t('pages.board.emptyTitle')}
          description={t('pages.board.emptyDescription')}
        >
          <Button
            onClick={() => openNewTask()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('tasks.new.title')}
          </Button>
        </EmptyState>
      </div>
    )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b px-5 py-3.5">
        <div role="tablist" className="flex rounded-lg border bg-subtle p-0.5">
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => setParams(v === 'status' ? {} : { vista: v }, { replace: true })}
              className={cn(
                'rounded-md px-3 py-1 text-[13px] text-muted-foreground',
                view === v && 'bg-card font-medium text-foreground shadow-sm',
              )}
            >
              {t(`board.views.${v}`)}
            </button>
          ))}
        </div>
        <span aria-hidden className="h-6 w-px bg-border" />
        <div className="flex flex-wrap gap-1.5" aria-label={t('runs.filters.project')}>
          <ChipButton active={!projectId} onClick={() => setProjectId(null)}>
            {t('board.allProjects')}
          </ChipButton>
          {projects.map((p) => (
            <ChipButton
              key={p.id}
              active={projectId === p.id}
              onClick={() => setProjectId(projectId === p.id ? null : p.id)}
            >
              <span className="size-2 rounded-[2px]" style={{ background: p.color }} />
              {p.name}
            </ChipButton>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[12.5px] text-muted-foreground">{t('board.agentFilter')}</span>
          <button
            type="button"
            aria-pressed={!agentId}
            aria-label={t('board.allAgents')}
            onClick={() => setAgentId(null)}
            className={cn(
              'grid size-6 place-items-center rounded-md border text-xs',
              !agentId && 'border-ring',
            )}
          >
            ∗
          </button>
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              aria-pressed={agentId === a.id}
              onClick={() => setAgentId(agentId === a.id ? null : a.id)}
              className={cn(
                'rounded-md border-2 border-transparent',
                agentId === a.id && 'border-ring',
                agentId && agentId !== a.id && 'opacity-45',
              )}
            >
              <AgentAvatar name={a.name} color={a.color} size={22} label={a.name} />
            </button>
          ))}
          <SchedulerSwitch />
          <Button
            onClick={() => openNewTask()}
            className="h-8 gap-1.5 bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Plus className="size-[15px]" />
            {t('header.primary.newTask')}
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-5">
        {/* By state a forked task counts once, with the state of its most pressing lane. */}
        {view === 'status' && <StatusColumns tasks={visible.filter((task) => !task.lane_of_id)} />}
        {/* By stage it is its lanes that sit in the columns of their stages. */}
        {view === 'stage' && (
          <StageColumns tasks={visible.filter((task) => task.phase !== 'forked')} />
        )}
        {view === 'queues' && (
          <AgentQueues
            agents={agentId ? agents.filter((a) => a.id === agentId) : agents}
            tasks={visible}
            allTasks={tasks.data ?? []}
          />
        )}
      </div>
    </div>
  )
}

function ChipButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[12.5px] font-medium',
        active && 'border-ring bg-accent',
      )}
    >
      {children}
    </button>
  )
}

function SchedulerSwitch() {
  const { t } = useTranslation()
  const state = useScheduler().data
  const setPaused = useSetSchedulerPaused()
  if (!state) return null
  return (
    <Button
      variant="outline"
      size="sm"
      aria-pressed={state.paused}
      title={state.paused ? t('board.paused') : undefined}
      onClick={() =>
        setPaused.mutate(!state.paused, { onError: (e) => toast.error(errorMessage(e)) })
      }
      className={cn(state.paused && 'border-status-waiting/50 text-status-waiting')}
    >
      {state.paused ? <Play /> : <Pause />}
      {state.paused ? t('board.resume') : t('board.pause')}
    </Button>
  )
}

function Column({
  title,
  dot,
  tasks,
  showStatus = false,
}: {
  title: string
  dot: string
  tasks: Task[]
  showStatus?: boolean
}) {
  const { t } = useTranslation()
  return (
    <section
      aria-label={title}
      className="flex w-[276px] shrink-0 flex-col gap-2 rounded-xl border bg-subtle p-2.5"
    >
      <h2 className="flex items-center gap-2 px-1 py-0.5 text-[13.5px] font-medium">
        <span className="size-2 rounded-full" style={{ background: dot }} />
        {title}
        <span className="font-mono text-[11.5px] text-muted-foreground">{tasks.length}</span>
      </h2>
      {tasks.length === 0 ? (
        <p className="px-1 py-3 text-center text-xs text-muted-foreground">
          {t('board.emptyColumn')}
        </p>
      ) : (
        tasks.map((task) => <TaskCard key={task.id} task={task} showStatus={showStatus} />)
      )}
    </section>
  )
}

function StatusColumns({ tasks }: { tasks: Task[] }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-full gap-3">
      {STATUS_COLUMNS.map((status) => {
        const column = tasks.filter((task) => task.status === status)
        return (
          <Column
            key={status}
            title={t(`tasks.status.${status}`)}
            dot={`var(--status-${TASK_TONE[status]})`}
            tasks={status === 'queued' ? queueOrder(column) : column}
          />
        )
      })}
    </div>
  )
}

function StageColumns({ tasks }: { tasks: Task[] }) {
  const { t } = useTranslation()
  // Stage names in pipeline order (several projects may share names such as «QA»).
  const names: string[] = []
  for (const task of [...tasks].sort((a, b) => a.stage_index - b.stage_index))
    if (task.stage_name && task.status !== 'done' && !names.includes(task.stage_name))
      names.push(task.stage_name)
  const open = tasks.filter((task) => task.status !== 'done')
  return (
    <div className="flex min-h-full gap-3">
      {names.map((name) => (
        <Column
          key={name}
          title={name}
          dot="var(--status-queued)"
          tasks={open.filter((task) => task.stage_name === name)}
          showStatus
        />
      ))}
      <Column
        title={t('board.noPipeline')}
        dot="var(--status-cancelled)"
        tasks={open.filter((task) => !task.stage_name)}
        showStatus
      />
      <Column
        title={t('tasks.status.done')}
        dot="var(--status-done)"
        tasks={tasks.filter((task) => task.status === 'done')}
      />
    </div>
  )
}

function AgentQueues({
  agents,
  tasks,
  allTasks,
}: {
  agents: Agent[]
  /** What the filters show. */
  tasks: Task[]
  /** Every task: a reorder always sends an agent's whole queue (the API rejects a part). */
  allTasks: Task[]
}) {
  const { t } = useTranslation()
  const visible = new Set(tasks.map((task) => task.id))
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12.5px] text-muted-foreground">{t('board.queuesHelp')}</p>
      {agents.map((agent) => (
        <AgentQueueRow
          key={agent.id}
          agent={agent}
          running={tasks.filter((task) => task.agent_id === agent.id && task.status === 'running')}
          queue={queueOrder(
            allTasks.filter((task) => task.agent_id === agent.id && task.status === 'queued'),
          )}
          visible={visible}
        />
      ))}
    </div>
  )
}

function AgentQueueRow({
  agent,
  running,
  queue,
  visible,
}: {
  agent: Agent
  running: Task[]
  /** The agent's whole queue, in the scheduler's order. */
  queue: Task[]
  visible: Set<string>
}) {
  const { t } = useTranslation()
  const reorder = useReorderQueue(agent.id)
  const [order, setOrder] = useState<string[] | null>(null)
  const ids = queue.map((task) => task.id)
  // While a reorder is saving, show the order the user chose.
  const full = order && order.length === ids.length ? order : ids
  const byId = new Map(queue.map((task) => [task.id, task]))
  const shown = full.filter((id) => visible.has(id))
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  /** Priority comes before position: a task only moves among tasks of its own priority. */
  const samePriority = (a: string, b: string | undefined) =>
    b !== undefined && byId.get(a)?.priority === byId.get(b)?.priority

  function move(fromId: string, toId: string | undefined) {
    if (!toId || fromId === toId || !samePriority(fromId, toId)) return
    const to = full.indexOf(toId)
    const next = arrayMove(full, full.indexOf(fromId), to)
    const task = byId.get(fromId)
    setOrder(next)
    reorder.mutate(next, {
      onSuccess: () =>
        toast.success(
          t('board.reordered', { name: agent.name, title: task?.title, position: to + 1 }),
        ),
      onError: (error) => toast.error(errorMessage(error)),
      onSettled: () => setOrder(null),
    })
  }

  function onDragEnd(event: DragEndEvent) {
    if (event.over) move(String(event.active.id), String(event.over.id))
  }

  return (
    <section
      aria-label={agent.name}
      className="grid grid-cols-[190px_minmax(0,1fr)] gap-4 rounded-xl border border-sep p-3.5 shadow-card bg-card-grad"
    >
      <div className="flex flex-col gap-1.5 border-r pr-3">
        <div className="flex items-center gap-2.5">
          <AgentAvatar name={agent.name} color={agent.color} size={30} />
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-medium">{agent.name}</div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {agent.role}
              <CliTag cli={agent.cli} label={t(`cli.${agent.cli}`)} size={16} />
            </div>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {t('board.queueStats', {
            running: running.length,
            queued: queue.length,
            max: agent.max_concurrency,
          })}
        </p>
      </div>
      {running.length === 0 && shown.length === 0 ? (
        <p className="grid place-items-center rounded-lg border border-dashed py-6 text-[12.5px] text-muted-foreground">
          {t('board.emptyQueue', { name: agent.name })}
        </p>
      ) : (
        <div className="flex flex-wrap gap-2.5">
          {running.map((task) => (
            <QueueCard key={task.id} task={task} label={t('board.now')} />
          ))}
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={shown} strategy={horizontalListSortingStrategy}>
              {shown.map((id, index) => {
                const task = byId.get(id)
                if (!task) return null
                const before = shown[index - 1]
                const after = shown[index + 1]
                return (
                  <SortableQueueCard
                    key={id}
                    task={task}
                    label={`#${full.indexOf(id) + 1}`}
                    onEarlier={samePriority(id, before) ? () => move(id, before) : undefined}
                    onLater={samePriority(id, after) ? () => move(id, after) : undefined}
                  />
                )
              })}
            </SortableContext>
          </DndContext>
        </div>
      )}
    </section>
  )
}

function SortableQueueCard({
  task,
  label,
  onEarlier,
  onLater,
}: {
  task: Task
  label: string
  onEarlier?: () => void
  onLater?: () => void
}) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.id,
  })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(isDragging && 'z-10 opacity-80')}
    >
      <QueueCard
        task={task}
        label={label}
        handle={
          <button
            type="button"
            aria-label={task.title}
            className="cursor-grab text-muted-foreground"
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-3.5" />
          </button>
        }
        controls={
          <span className="ml-auto flex">
            <button
              type="button"
              aria-label={t('board.moveEarlier', { title: task.title })}
              disabled={!onEarlier}
              onClick={onEarlier}
              className="text-muted-foreground disabled:opacity-30"
            >
              <ChevronLeft className="size-3.5" />
            </button>
            <button
              type="button"
              aria-label={t('board.moveLater', { title: task.title })}
              disabled={!onLater}
              onClick={onLater}
              className="text-muted-foreground disabled:opacity-30"
            >
              <ChevronRight className="size-3.5" />
            </button>
          </span>
        }
      />
    </div>
  )
}

/** Card of an agent's queue (design 07c). */
function QueueCard({
  task,
  label,
  handle,
  controls,
}: {
  task: Task
  label: string
  handle?: React.ReactNode
  controls?: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <article
      aria-label={`${label} ${task.code}`}
      className={cn(
        'flex w-[228px] flex-col gap-1 rounded-[10px] border bg-subtle px-3 py-2.5',
        task.status === 'running' && 'border-status-running/60',
      )}
    >
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {handle}
        <span className="font-mono font-bold text-foreground">{label}</span>
        <span className="size-1.5 rounded-[2px]" style={{ background: task.project_color }} />
        <span className="truncate">{task.project_name}</span>
        {controls}
        {!controls && (
          <span className="ml-auto">
            <TaskStatusBadge status={task.status} size="xs" />
          </span>
        )}
      </div>
      <Link
        to={`/tablero/tareas/${task.id}`}
        className="line-clamp-2 text-[13.5px] font-medium hover:underline"
      >
        {task.title}
      </Link>
      <div className="text-[11.5px] text-muted-foreground">
        {task.stage_name ?? t('tasks.noStage')}
        {task.lane_name && ` · ${t('tasks.lanes.laneTag', { name: task.lane_name })}`} ·{' '}
        <PriorityLabel priority={task.priority} />
        {task.blocked && (
          <span className="text-status-waiting">
            {' '}
            · {t(`tasks.blocked.${task.blocked}`, { account: task.blocked_by ?? '' })}
          </span>
        )}
      </div>
    </article>
  )
}
