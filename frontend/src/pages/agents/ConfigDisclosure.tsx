import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { accountOf, useAccounts } from '@/api/accounts'
import { useTeams } from '@/api/teams'
import type { Agent } from '@/api/types'

/** The agent's set-up, folded at the end of its page: read-only, edited in the other tabs. */
export function ConfigDisclosure({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const accounts = useAccounts().data
  const teams = useTeams().data
  const account = accountOf(accounts, agent)
  const team = teams?.find((x) => x.id === agent.team_id)
  const items: [string, string][] = [
    [t('agents.fields.team'), team?.name ?? t('teams.none')],
    [t('agents.fields.cli'), t(`cli.${agent.cli}`)],
    [t('agents.fields.account'), account?.name ?? '—'],
    [t('agents.fields.model'), agent.model || t('cli.defaultModel')],
    [t('agents.fields.permissions'), t(`agents.permission.${agent.permission_mode}`)],
    [t('agents.fields.concurrency'), String(agent.max_concurrency)],
  ]
  return (
    <details className="group border-t border-sep pt-4">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
        <span className="font-medium">{t('agents.summary.config')}</span>
        <span className="text-xs text-muted-foreground">{t('agents.summary.configHint')}</span>
      </summary>
      <dl className="mt-4 grid grid-cols-3 gap-x-6 gap-y-3 max-md:grid-cols-2">
        {items.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="truncate text-[13px]">{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}
