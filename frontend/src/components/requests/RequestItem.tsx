import {
  AlertTriangle,
  BatteryWarning,
  CheckCheck,
  Clock,
  Gauge,
  HelpCircle,
  Inbox,
  OctagonAlert,
  PackageCheck,
  ShieldCheck,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { InboxItem, InboxKind } from '@/api/types'
import { AgentAvatar, ProjectChip } from '@/components/agentic/primitives'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { RequestActions } from './RequestActions'

const PROMPT = '❯ '

export const KIND_STYLE: Record<InboxKind, { color: string; icon: typeof Inbox }> = {
  approval: { color: 'var(--status-waiting)', icon: ShieldCheck },
  question: { color: 'var(--status-running)', icon: HelpCircle },
  blocker: { color: 'var(--status-failed)', icon: OctagonAlert },
  review: { color: 'var(--status-review)', icon: CheckCheck },
  stalled: { color: 'var(--status-waiting)', icon: Clock },
  attention: { color: 'var(--status-failed)', icon: AlertTriangle },
  delivery: { color: 'var(--status-done)', icon: PackageCheck },
  limit: { color: 'var(--status-waiting)', icon: Gauge },
  quota: { color: 'var(--status-failed)', icon: BatteryWarning },
}

/** A request of the agents to the person, with its actions while pending. */
export function RequestItem({ item, focused = false }: { item: InboxItem; focused?: boolean }) {
  const { t } = useTranslation()
  const style = KIND_STYLE[item.kind]
  const Icon = style.icon
  const title = item.kind === 'approval' ? t('inbox.approvalTitle') : item.title
  return (
    <article
      aria-label={`${t(`inbox.kinds.${item.kind}`)}: ${title}`}
      className={cn(
        'overflow-hidden rounded-xl border bg-card',
        focused && 'border-ring ring-1 ring-ring',
      )}
    >
      <div className="flex gap-3 px-4 py-3.5">
        <div className="relative h-fit">
          <AgentAvatar name={item.agent_name || '?'} color={item.agent_color} size={34} />
          <span
            className="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full border bg-card"
            style={{ color: style.color }}
          >
            <Icon className="size-2.5" />
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
            <span className="font-medium" style={{ color: style.color }}>
              {t(`inbox.kinds.${item.kind}`)}
            </span>
            {item.agent_name && (
              <>
                · <span className="font-medium text-foreground">{item.agent_name}</span>
              </>
            )}
            {item.project_name && (
              <>
                · <ProjectChip name={item.project_name} color={item.project_color} variant="dot" />
              </>
            )}
            {item.task_id && (
              <>
                ·{' '}
                <Link to={`/tablero/tareas/${item.task_id}`} className="text-ring hover:underline">
                  {item.task_code ? `${item.task_code} · ${item.task_title ?? ''}` : ''}
                </Link>
              </>
            )}
            <time className="ml-auto" dateTime={item.created_at}>
              {relativeTime(item.created_at)}
            </time>
          </div>
          <h2 className="mt-1 text-[15px] font-medium">{title}</h2>
          {item.kind === 'approval' && item.command && (
            <pre className="mt-2 overflow-x-auto rounded-md bg-terminal px-3 py-2 font-mono text-[13px] text-terminal-foreground">
              <span aria-hidden className="text-[#7F8DAA]">
                {PROMPT}
              </span>
              {item.command}
            </pre>
          )}
          {item.detail && (
            <p className="mt-1.5 text-[13px] whitespace-pre-wrap text-muted-foreground">
              {item.detail}
            </p>
          )}
          {item.status === 'resolved' && item.resolution && (
            <p className="mt-2 text-[13px] text-status-done">
              {t(`inbox.resolution.${item.resolution}`, { text: item.response ?? '' })}
            </p>
          )}
        </div>
      </div>
      {item.status === 'pending' && <RequestActions item={item} />}
    </article>
  )
}
