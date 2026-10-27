import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import type { AgentState, HomeAgent, HomeSession, TodayAgent } from '@/api/types'
import { AgentAvatar, CLI_TAG } from '@/components/agentic/primitives'
import { useNow } from '@/hooks/use-now'
import { formatTokens, formatUsd } from '@/lib/format'
import { formatDuration } from '@/lib/time'
import { cn } from '@/lib/utils'
import { useDialogs } from '@/stores/dialogs'

const STATE_COLOR: Record<AgentState, string> = {
  running: 'text-status-running',
  waiting: 'text-status-waiting',
  idle: 'text-status-done',
  draft: 'text-status-review',
}

function SessionRow({ session, waiting }: { session: HomeSession; waiting: boolean }) {
  const { t } = useTranslation()
  const live = session.status === 'running' || session.status === 'intervening'
  const now = useNow(live && !waiting ? 1000 : null)
  const label = session.resumable
    ? t('home.agents.session.resumable')
    : waiting
      ? t('home.agents.session.waiting')
      : session.status === 'starting'
        ? t('home.agents.session.starting')
        : formatDuration(session.started_at ?? session.created_at, null, now)
  const dot = session.resumable
    ? 'bg-status-failed'
    : waiting
      ? 'bg-status-waiting'
      : session.status === 'starting'
        ? 'bg-status-queued'
        : 'bg-status-running animate-live-pulse'
  const title = session.task_title ?? session.project_name
  return (
    <Link
      to={session.task_id ? `/tablero/tareas/${session.task_id}` : `/ejecuciones/${session.run_id}`}
      onClick={(e) => e.stopPropagation()}
      title={`${title} · ${session.project_name}`}
      className="-mx-1.5 flex h-6 min-w-0 items-center gap-2 rounded-[7px] px-1.5 whitespace-nowrap text-foreground hover:bg-subtle"
    >
      <span className={cn('size-1.5 shrink-0 rounded-full', dot)} />
      {session.task_code && (
        <span className="shrink-0 font-mono text-xs text-muted-foreground">
          {session.task_code}
        </span>
      )}
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {session.project_color && (
        <span
          className="size-[7px] shrink-0 rounded-[2px]"
          style={{ background: session.project_color }}
        />
      )}
      <span className="shrink-0 font-mono text-xs text-muted-foreground">{label}</span>
    </Link>
  )
}

/** One agent: its state, its live sessions and, on hover, what it spent today. */
export function AgentCard({
  agent,
  highlighted,
  usage,
  maxCost,
  waitingRuns,
}: {
  agent: HomeAgent
  /** A request of this agent is being hovered in «Te necesitan». */
  highlighted: boolean
  usage?: TodayAgent
  /** The most any agent spent today, for the little bar. */
  maxCost: number
  /** Runs with a pending request: they wait for the person. */
  waitingRuns: Set<string>
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const openNewTask = useDialogs((s) => s.openNewTask)
  const open = () => void navigate(`/agentes/${agent.id}`)
  const queued =
    agent.queued > 0
      ? t('home.agents.queued', { count: agent.queued })
      : t('home.agents.queueEmpty')
  const spent = usage ? (usage.cost_usd > 0 ? formatUsd(usage.cost_usd) : '—') : '—'
  const share = usage && maxCost > 0 ? Math.max((usage.cost_usd / maxCost) * 100, 1) : 1

  return (
    <div
      role="link"
      tabIndex={0}
      aria-label={`${agent.name}, ${agent.role}. ${t(`home.agents.states.${agent.state}`)}`}
      onClick={open}
      onKeyDown={(e) => e.key === 'Enter' && e.target === e.currentTarget && open()}
      className={cn(
        'group relative flex cursor-pointer flex-col gap-2 rounded-2xl border px-3.5 pt-[13px] pb-2.5 shadow-card bg-card-grad hover:-translate-y-px hover:border-ring',
        highlighted
          ? 'border-status-waiting shadow-[0_0_0_3px_color-mix(in_oklch,var(--status-waiting)_30%,transparent),var(--shadow-card)]'
          : agent.pending_requests > 0
            ? 'border-[color-mix(in_oklch,var(--status-waiting)_55%,var(--border))]'
            : 'border-sep',
      )}
    >
      {agent.state === 'running' && (
        <span
          aria-hidden
          className="absolute inset-x-4 -top-px h-0.5 animate-sweep rounded-sm bg-[linear-gradient(90deg,transparent_0,var(--status-running)_50%,transparent_100%)] bg-[length:50%_100%] bg-no-repeat"
        />
      )}
      {agent.pending_requests > 0 && (
        <span className="absolute -top-[9px] right-3 flex h-[18px] items-center rounded-full bg-status-intervening px-2 text-[10.5px] font-bold text-status-intervening-foreground shadow-[0_0_0_3px_var(--background)]">
          {t('home.agents.requests', { count: agent.pending_requests })}
        </span>
      )}

      <div className="flex min-w-0 items-center gap-2.5">
        <AgentAvatar name={agent.name} color={agent.color} size={30} />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{agent.name}</span>
        <span
          className={cn(
            'flex shrink-0 items-center gap-[5px] text-xs font-medium whitespace-nowrap',
            STATE_COLOR[agent.state],
          )}
        >
          <span
            className={cn(
              'size-1.5 rounded-full bg-current',
              agent.state === 'running' && 'animate-live-pulse',
            )}
          />
          {t(`home.agents.states.${agent.state}`)}
        </span>
      </div>

      <div className="flex min-h-6 min-w-0 flex-col gap-0.5">
        {agent.sessions.map((session) => (
          <SessionRow
            key={session.run_id}
            session={session}
            waiting={waitingRuns.has(session.run_id)}
          />
        ))}
        {agent.sessions.length === 0 && (
          <div className="flex h-6 items-center truncate text-muted-foreground">
            {agent.state === 'draft' ? t('home.agents.draft') : t('home.agents.free')}
          </div>
        )}
      </div>

      {/* Secondary line and spend share a cell: hover or focus swaps them. */}
      <div className="grid items-center">
        <div className="col-start-1 row-start-1 flex h-7 items-center gap-1.5 overflow-hidden text-xs whitespace-nowrap text-muted-foreground transition-opacity duration-150 group-focus-within:opacity-0 group-hover:opacity-0">
          <span className="truncate">{agent.role}</span>
          <span>·</span>
          <span className="font-mono">{CLI_TAG[agent.cli]}</span>
          {agent.using_fallback && (
            <span className="rounded-full bg-subtle px-1.5 text-[10.5px] font-medium text-status-waiting">
              {t('home.agents.usingFallback')}
            </span>
          )}
          <span>·</span>
          <span>{queued}</span>
        </div>
        <div className="pointer-events-none col-start-1 row-start-1 flex gap-1.5 opacity-0 transition-opacity duration-150 group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100">
          <Link
            to={`/consumo`}
            onClick={(e) => e.stopPropagation()}
            title={t('home.agents.usage')}
            className="flex h-7 min-w-0 flex-1 items-center gap-2 rounded-full bg-subtle px-2.5 text-[11.5px] whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <strong className="font-mono font-medium text-foreground">{spent}</strong>
            <span>{t('home.agents.tokens', { value: formatTokens(usage?.tokens ?? 0) })}</span>
            <span className="h-1 min-w-6 flex-1 overflow-hidden rounded-full bg-muted">
              <span className="block h-full bg-muted-foreground" style={{ width: `${share}%` }} />
            </span>
            <span>{queued}</span>
          </Link>
          {agent.state !== 'draft' && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                openNewTask({ agentId: agent.id })
              }}
              aria-label={t('home.agents.assign', { name: agent.name })}
              title={t('home.agents.assign', { name: agent.name })}
              className="grid size-7 shrink-0 place-items-center rounded-full bg-subtle text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Plus className="size-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
