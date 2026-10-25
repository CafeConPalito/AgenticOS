import { useTranslation } from 'react-i18next'
import { useRunConnections } from '@/api/connections'
import { cn } from '@/lib/utils'

const STATUS_CLASS: Record<string, string> = {
  connected: 'bg-status-completed/15 text-status-completed',
  sent: 'bg-subtle text-muted-foreground',
  failed: 'bg-status-failed/15 text-status-failed',
  skipped: 'bg-status-waiting/15 text-status-waiting',
}

/**
 * «Conexiones MCP» of a run's page: the external servers it was given (and why one was not),
 * and the calls the agent made to their tools, apart from the calls to Agentic OS (CA11, CA13).
 */
export function RunConnectionsPanel({ runId }: { runId: string }) {
  const { t } = useTranslation()
  const { data } = useRunConnections(runId)
  if (!data || data.connections.length === 0) return null
  return (
    <section aria-label={t('connections.run.title')} className="mb-4 grid gap-2">
      <h3 className="text-[12.5px] font-medium text-muted-foreground">
        {t('connections.run.title')}
      </h3>
      <ul className="grid gap-1.5">
        {data.connections.map((connection) => (
          <li key={connection.name} className="grid gap-0.5 text-[12.5px]">
            <div className="flex items-center gap-2">
              <span className="font-mono">{connection.name}</span>
              <span className={cn('rounded px-1.5 text-[11px]', STATUS_CLASS[connection.status])}>
                {t(`connections.run.status_${connection.status}`)}
              </span>
              {connection.calls > 0 && (
                <span className="ml-auto text-muted-foreground">
                  {t('connections.run.calls', { count: connection.calls })}
                  {connection.failed_calls > 0 &&
                    ` · ${t('connections.run.failedCalls', { count: connection.failed_calls })}`}
                </span>
              )}
            </div>
            {connection.detail && (
              <p className="text-[12px] text-muted-foreground">{connection.detail}</p>
            )}
          </li>
        ))}
      </ul>
      {data.calls.length > 0 && (
        <ol
          aria-label={t('connections.run.callsTitle')}
          className="grid gap-1 font-mono text-[12px]"
        >
          {data.calls.map((call) => (
            <li key={call.id} className="flex items-baseline gap-2">
              <span>
                {call.connection}/{call.tool}
              </span>
              <span className="text-muted-foreground">
                {call.duration_ms !== null ? `${call.duration_ms} ms` : '…'}
              </span>
              {call.ok === false && (
                <span className="truncate text-status-failed" title={call.error}>
                  {call.error || t('connections.run.failed')}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
