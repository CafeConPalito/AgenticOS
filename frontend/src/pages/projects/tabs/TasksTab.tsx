import { ListChecks, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatTokens, formatUsd, totalTokens } from '@/lib/format'
import { useNavigate } from 'react-router'
import { useTasks } from '@/api/tasks'
import type { Project } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useDialogs } from '@/stores/dialogs'
import { PriorityLabel, TaskAgent, TaskStatusBadge } from '@/pages/tasks/TaskBits'

export function TasksTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const tasks = useTasks({ projectId: project.id })
  const openNewTask = useDialogs((s) => s.openNewTask)

  return (
    <div className="flex flex-col gap-3 px-6 pt-5 pb-8">
      <div className="flex justify-end">
        <Button
          onClick={() => openNewTask({ projectId: project.id })}
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          <Plus />
          {t('tasks.new.title')}
        </Button>
      </div>
      {tasks.data && tasks.data.length === 0 ? (
        <EmptyState icon={ListChecks} title={t('tasks.empty')} />
      ) : (
        <div className="overflow-hidden rounded-xl border border-sep shadow-card bg-card-grad">
          <Table>
            <TableHeader className="bg-subtle">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-20 px-4">{t('tasks.columns.id')}</TableHead>
                <TableHead>{t('tasks.columns.task')}</TableHead>
                <TableHead>{t('tasks.columns.stage')}</TableHead>
                <TableHead>{t('tasks.columns.status')}</TableHead>
                <TableHead>{t('tasks.columns.agent')}</TableHead>
                <TableHead>{t('tasks.columns.priority')}</TableHead>
                <TableHead className="text-right">{t('tasks.columns.cost')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(tasks.data ?? []).map((task) => {
                const open = () => navigate(`/tablero/tareas/${task.id}`)
                return (
                  <TableRow
                    key={task.id}
                    tabIndex={0}
                    aria-label={t('tasks.open', { code: task.code, title: task.title })}
                    onClick={open}
                    onKeyDown={(e) => e.key === 'Enter' && open()}
                    className="cursor-pointer"
                  >
                    <TableCell className="px-4 font-mono text-xs text-muted-foreground">
                      {task.code}
                    </TableCell>
                    <TableCell className="max-w-[360px] truncate font-medium">
                      {task.title}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {task.stage_name ?? t('tasks.noStage')}
                    </TableCell>
                    <TableCell>
                      <TaskStatusBadge status={task.status} size="sm" />
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2">
                        <TaskAgent task={task} />
                        {task.agent_name}
                      </span>
                    </TableCell>
                    <TableCell>
                      <PriorityLabel priority={task.priority} />
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {task.usage.cost_usd !== null
                        ? formatUsd(task.usage.cost_usd)
                        : totalTokens(task.usage) > 0
                          ? formatTokens(totalTokens(task.usage))
                          : t('common.none')}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
