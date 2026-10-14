import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useInbox } from '@/api/inbox'
import { useTasks } from '@/api/tasks'
import type { Agent } from '@/api/types'
import { useUsageBreakdown } from '@/api/usage'
import { ProjectChip } from '@/components/agentic/primitives'
import { RequestItem } from '@/components/requests/RequestItem'
import { Skeleton } from '@/components/ui/skeleton'
import { formatTokens, formatUsd } from '@/lib/format'
import { TaskStatusBadge } from '@/pages/tasks/TaskBits'
import { ConfigDisclosure } from '../ConfigDisclosure'

const OPEN_TASKS = 8

/** The agent at a glance: what it asks of the person, its tasks, its spend and its set-up. */
export function SummaryTab({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const pending = useInbox('pending').data
  const requests = (Array.isArray(pending) ? pending : []).filter(
    (item) => item.agent_id === agent.id,
  )
  const tasksQuery = useTasks({ agentId: agent.id })
  const tasks = (Array.isArray(tasksQuery.data) ? tasksQuery.data : []).filter(
    (task) => task.status !== 'done' && task.status !== 'cancelled',
  )
  const usage = useUsageBreakdown({ days: 30 }, 'agent').data
  const row = usage?.rows?.find((r) => r.id === agent.id)

  return (
    <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-6 pt-5 pb-8">
      {requests.length > 0 && (
        <section aria-label={t('agents.summary.requests')} className="flex flex-col gap-3">
          {requests.map((item) => (
            <div
              key={item.id}
              className="rounded-xl ring-1 ring-[color-mix(in_oklch,var(--status-waiting)_50%,transparent)]"
            >
              <RequestItem item={item} />
            </div>
          ))}
        </section>
      )}

      <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] items-start gap-6 max-lg:grid-cols-1">
        <section aria-labelledby="agent-tasks" className="flex flex-col gap-2.5">
          <h2 id="agent-tasks" className="eyebrow">
            {t('agents.summary.tasks')}
          </h2>
          {tasksQuery.isPending ? (
            <Skeleton aria-busy className="h-24 rounded-xl" />
          ) : tasks.length === 0 ? (
            <p className="text-muted-foreground">{t('agents.summary.noTasks')}</p>
          ) : (
            <ul className="flex flex-col">
              {tasks.slice(0, OPEN_TASKS).map((task) => (
                <li key={task.id}>
                  <Link
                    to={`/tablero/tareas/${task.id}`}
                    className="-mx-2 flex items-center gap-2.5 rounded-[9px] px-2 py-2 hover:bg-subtle"
                  >
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {task.code}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{task.title}</span>
                    <ProjectChip name={task.project_name} color={task.project_color} />
                    <TaskStatusBadge status={task.status} size="xs" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {tasks.length > OPEN_TASKS && (
            <Link to="/tablero?vista=queues" className="text-xs text-ring hover:underline">
              {t('agents.summary.moreTasks', { count: tasks.length - OPEN_TASKS })}
            </Link>
          )}
        </section>

        <section aria-labelledby="agent-usage" className="flex flex-col gap-2.5">
          <h2 id="agent-usage" className="eyebrow">
            {t('agents.summary.usage')}
          </h2>
          {row ? (
            <dl className="grid grid-cols-3 gap-3">
              <div>
                <dt className="text-xs text-muted-foreground">{t('usage.columns.cost')}</dt>
                <dd className="font-mono text-lg font-medium">
                  {row.cost_usd > 0 ? formatUsd(row.cost_usd) : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">{t('usage.columns.tokens')}</dt>
                <dd className="font-mono text-lg font-medium">{formatTokens(row.tokens)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">{t('agents.summary.sessions')}</dt>
                <dd className="font-mono text-lg font-medium">{row.sessions}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-muted-foreground">{t('agents.summary.noUsage')}</p>
          )}
          <p className="text-xs text-muted-foreground">{t('agents.summary.period')}</p>
          <Link to="/consumo" className="w-fit text-xs text-ring hover:underline">
            {t('home.agents.usage')}
          </Link>
        </section>
      </div>

      <ConfigDisclosure agent={agent} />
    </div>
  )
}
