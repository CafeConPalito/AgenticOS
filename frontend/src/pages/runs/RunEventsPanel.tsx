import { useTranslation } from 'react-i18next'
import { useRunEvents } from '@/api/runs'
import type { RunEvent } from '@/api/types'
import type es from '@/i18n/es.json'
import { cn } from '@/lib/utils'

type EventName = keyof typeof es.runs.events.names

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}

/** «Eventos MCP» column of the run page (design 09a): what the agent reported, live. */
export function RunEventsPanel({ runId }: { runId: string }) {
  const { t } = useTranslation()
  const { data: events = [] } = useRunEvents(runId)

  return (
    <section aria-labelledby="run-events-title" className="flex min-h-0 flex-col gap-2.5">
      <h2 id="run-events-title" className="text-[12.5px] text-muted-foreground">
        {t('runs.events.title')}
      </h2>
      {events.length === 0 ? (
        <p className="text-[12.5px] text-muted-foreground">{t('runs.events.empty')}</p>
      ) : (
        <ol className="grid grid-cols-[40px_minmax(0,1fr)] gap-x-2 gap-y-2.5 text-[12.5px]">
          {events.map((event) => (
            <EventRow key={event.id} event={event} />
          ))}
        </ol>
      )}
    </section>
  )
}

function EventRow({ event }: { event: RunEvent }) {
  const { t } = useTranslation()
  const label = t(`runs.events.names.${event.name as EventName}`, { defaultValue: '' })
  return (
    <li className="contents">
      <time dateTime={event.at} className="font-mono text-[11.5px] text-muted-foreground">
        {time(event.at)}
      </time>
      <p className="min-w-0 break-words">
        {event.kind === 'mcp' ? (
          <>
            <span className="font-mono text-[12px] text-status-review">{event.name}</span>
            {event.detail && <span>: {event.detail}</span>}
          </>
        ) : (
          <span className={cn('text-muted-foreground', event.kind === 'hook' && 'italic')}>
            {label || event.name}
            {event.detail && event.name !== 'closing' && ` · ${event.detail}`}
          </span>
        )}
      </p>
    </li>
  )
}
