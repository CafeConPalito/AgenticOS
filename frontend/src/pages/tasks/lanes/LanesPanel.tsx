import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useAddLane, useTaskAction } from '@/api/tasks'
import type { Lane, Pipeline, Task } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { errorMessage } from '@/lib/form-errors'
import { TaskStatusBadge } from '../TaskBits'
import { NEUTRAL_COLOR } from '@/theme/palettes'

const ACTIVE = (lane: Lane) => !['done', 'cancelled'].includes(lane.status)

/** The branches a task took: their state, cancel one, add one the decision left out. */
export function LanesPanel({ task, pipeline }: { task: Task; pipeline: Pipeline | undefined }) {
  const { t } = useTranslation()
  const add = useAddLane(task.id)
  const [cancelling, setCancelling] = useState<Lane | null>(null)
  if (task.lanes.length === 0) return null

  const fork = task.phase === 'forked' ? task.stage_id : null
  const addable = fork
    ? (pipeline?.links ?? []).filter(
        (l) =>
          l.from_stage_id === fork &&
          !task.lanes.some((lane) => lane.link_id === l.id && ACTIVE(lane)),
      )
    : []

  return (
    <section aria-labelledby="lanes-title" className="flex flex-col gap-2">
      <h2 id="lanes-title" className="text-[12.5px] text-muted-foreground">
        {t('tasks.lanes.title')}
      </h2>
      <ul className="grid gap-1.5">
        {task.lanes.map((lane) => (
          <li key={lane.id} className="flex items-center gap-2 rounded-lg border px-2.5 py-1.5">
            {lane.agent_name && (
              <AgentAvatar
                name={lane.agent_name}
                agentId={lane.agent_id}
                color={lane.agent_color ?? NEUTRAL_COLOR}
                size={18}
              />
            )}
            <div className="min-w-0 flex-1">
              <Link to={`/tablero/tareas/${lane.id}`} className="block truncate hover:underline">
                {lane.name}
              </Link>
              <span className="block truncate text-xs text-muted-foreground">
                {lane.stage_name ?? '—'}
                {lane.waiting_reason && ` · ${t(`tasks.waiting.${lane.waiting_reason}`)}`}
              </span>
            </div>
            <TaskStatusBadge status={lane.status} />
            {ACTIVE(lane) && (
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t('tasks.lanes.cancelLane', { name: lane.name })}
                onClick={() => setCancelling(lane)}
              >
                <X />
              </Button>
            )}
          </li>
        ))}
      </ul>
      {addable.length > 0 && (
        <Select
          value=""
          onValueChange={(linkId) =>
            add.mutate(linkId, { onError: (error) => toast.error(errorMessage(error)) })
          }
        >
          <SelectTrigger
            aria-label={t('tasks.lanes.add')}
            className="h-8 w-full border-dashed text-[13px]"
          >
            <Plus className="size-3.5" />
            <SelectValue placeholder={t('tasks.lanes.add')} />
          </SelectTrigger>
          <SelectContent>
            {addable.map((l) => (
              <SelectItem key={l.id} value={l.id}>
                {l.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {cancelling && <CancelLane lane={cancelling} onClose={() => setCancelling(null)} />}
    </section>
  )
}

function CancelLane({ lane, onClose }: { lane: Lane; onClose: () => void }) {
  const { t } = useTranslation()
  const act = useTaskAction(lane.id)
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={t('tasks.lanes.cancelTitle', { name: lane.name })}
      description={t('tasks.lanes.cancelDescription')}
      confirmLabel={t('tasks.lanes.cancelConfirm')}
      destructive
      onConfirm={() =>
        act.mutate(
          { action: 'cancel' },
          { onError: (error) => toast.error(errorMessage(error)), onSettled: onClose },
        )
      }
    />
  )
}
