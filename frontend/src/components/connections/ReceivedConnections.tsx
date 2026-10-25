import { Plug } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ConnectionsPreview } from '@/api/connections'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

/** Tokens past which a warning is worth showing: the tools of every server weigh on the context. */
const HEAVY = 8_000

/**
 * The connections an agent (or a pipeline stage) receives: each one with the level it comes from
 * and a switch to take it away from there (CA5, CA6). The totals say how much context the tools
 * of all of them cost.
 */
export function ReceivedConnections({
  preview,
  excludedIds,
  onChange,
  scope,
}: {
  preview: ConnectionsPreview
  excludedIds: string[]
  onChange: (excluded: string[]) => void
  /** Where the switch takes it away from: this agent or this stage. */
  scope: 'agent' | 'stage'
}) {
  const { t } = useTranslation()
  const rows = [
    ...preview.effective.map((e) => ({ ...e, on: true, reason: null as string | null })),
    ...preview.excluded
      .filter((x) => x.reason === scope || x.reason === 'disabled')
      .map((x) => ({
        connection: x.connection,
        level: x.level,
        tools: 0,
        tokens: 0,
        on: false,
        reason: x.reason,
      })),
  ].sort((a, b) => a.connection.name.localeCompare(b.connection.name))

  const toggle = (id: string, on: boolean) =>
    onChange(on ? excludedIds.filter((x) => x !== id) : [...new Set([...excludedIds, id])])

  if (rows.length === 0) {
    return (
      <p className="text-[13px] text-muted-foreground">{t(`connections.received.none_${scope}`)}</p>
    )
  }
  return (
    <div className="grid gap-3">
      <ul className="grid gap-2">
        {rows.map((row) => (
          <li
            key={row.connection.id}
            className={cn(
              'flex items-center gap-3 rounded-lg border px-3 py-2 text-[13px]',
              !row.on && 'opacity-60',
            )}
          >
            <Plug className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <span className="font-mono font-medium">{row.connection.name}</span>
              <span className="ml-2 text-[12px] text-muted-foreground">
                {t(`connections.level.${row.level}`)}
                {row.on
                  ? ` · ${t('connections.received.cost', { tools: row.tools, tokens: row.tokens })}`
                  : row.reason === 'disabled'
                    ? ` · ${t('connections.received.disabled')}`
                    : ` · ${t(`connections.received.taken_${scope}`)}`}
              </span>
            </div>
            {row.reason !== 'disabled' && (
              <Switch
                checked={row.on}
                aria-label={t(`connections.received.switch_${scope}`, {
                  name: row.connection.name,
                })}
                onCheckedChange={(on) => toggle(row.connection.id, on)}
              />
            )}
          </li>
        ))}
      </ul>
      <p
        className={cn(
          'text-[12.5px] text-muted-foreground',
          preview.total_tokens > HEAVY && 'text-status-waiting',
        )}
      >
        {t('connections.received.total', {
          tools: preview.total_tools,
          tokens: preview.total_tokens,
        })}
        {preview.total_tokens > HEAVY && ` ${t('connections.received.heavy')}`}
      </p>
    </div>
  )
}
