import { AlertTriangle, CircleCheck, KeyRound, Plug, Wrench } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { type Connection, useUpdateConnection } from '@/api/connections'
import { Switch } from '@/components/ui/switch'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { useLevelName } from './shared'

/** One connection of the catalog: its switch, where it comes from, whether it works, and use. */
export function ConnectionCard({
  connection,
  onOpen,
}: {
  connection: Connection
  onOpen: (id: string) => void
}) {
  const { t } = useTranslation()
  const toggle = useUpdateConnection()
  const levelName = useLevelName()
  const missing = connection.secrets.filter((s) => !s.set)
  const login = connection.oauth?.status
  const needsLogin = connection.auth === 'oauth' && login !== 'connected'
  return (
    <article
      className={cn(
        'flex flex-col gap-2 rounded-xl border border-sep p-3.5 shadow-card bg-card-grad',
        !connection.enabled && 'opacity-60',
      )}
    >
      <div className="flex items-start gap-2.5">
        <Plug className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <button
          type="button"
          onClick={() => onOpen(connection.id)}
          aria-label={t('connections.actions.open', { name: connection.name })}
          className="min-w-0 flex-1 text-left"
        >
          <span className="block truncate font-mono text-[13px] font-medium">
            {connection.name}
          </span>
          <span className="line-clamp-2 text-[12.5px] text-muted-foreground">
            {connection.description || connection.command || connection.url}
          </span>
        </button>
        <Switch
          checked={connection.enabled}
          aria-label={t('connections.actions.enable', { name: connection.name })}
          onCheckedChange={(enabled) => toggle.mutate({ id: connection.id, enabled })}
        />
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted-foreground">
        <span className="rounded bg-subtle px-1.5">
          {t(`connections.transport.${connection.transport}`)}
        </span>
        {connection.origin !== 'user' && (
          <span className="rounded bg-subtle px-1.5">
            {t(`connections.origin.${connection.origin}`)}
          </span>
        )}
        {connection.assignments.length === 0 ? (
          <span className="rounded bg-subtle px-1.5">{t('connections.card.unassigned')}</span>
        ) : (
          connection.assignments.slice(0, 2).map((a) => (
            <span key={a.id} className="rounded bg-subtle px-1.5">
              {levelName(a)}
            </span>
          ))
        )}
        {connection.assignments.length > 2 && <span>+{connection.assignments.length - 2}</span>}
        {needsLogin && (
          <span className="flex items-center gap-1 rounded bg-status-waiting/15 px-1.5 text-status-waiting">
            <KeyRound className="size-3" aria-hidden />
            {login === 'needs_reauth'
              ? t('connections.card.reconnect')
              : t('connections.card.connect')}
          </span>
        )}
        {missing.length > 0 && (
          <span className="flex items-center gap-1 rounded bg-status-waiting/15 px-1.5 text-status-waiting">
            <KeyRound className="size-3" aria-hidden />
            {t('connections.card.missingSecret', { count: missing.length })}
          </span>
        )}
        {connection.tools_changed && (
          <span className="rounded bg-status-running/15 px-1.5 text-status-running">
            {t('connections.card.newTools')}
          </span>
        )}
        {connection.registry?.update_available && (
          <span className="rounded bg-status-running/15 px-1.5 text-status-running">
            {t('connections.card.update')}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-muted-foreground">
        {connection.test_error ? (
          <span className="flex items-center gap-1 text-status-failed">
            <AlertTriangle className="size-3" aria-hidden />
            {t('connections.card.testFailed')}
          </span>
        ) : connection.tested_at ? (
          <span className="flex items-center gap-1">
            <CircleCheck className="text-status-completed size-3" aria-hidden />
            {t('connections.card.tested', { count: connection.tools.length })}
          </span>
        ) : (
          <span>{t('connections.card.untested')}</span>
        )}
        <span className="ml-auto flex items-center gap-1">
          {connection.usage.calls > 0 && <Wrench className="size-3" aria-hidden />}
          {connection.usage.calls > 0
            ? `${t('connections.card.used', {
                runs: connection.usage.used_runs,
                calls: connection.usage.calls,
              })}${
                connection.usage.last_used
                  ? ` · ${t('connections.card.lastUsed', { when: relativeTime(connection.usage.last_used) })}`
                  : ''
              }`
            : t('connections.card.neverUsed')}
        </span>
      </div>
    </article>
  )
}
