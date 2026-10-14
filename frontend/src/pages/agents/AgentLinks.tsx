import { useTranslation } from 'react-i18next'
import { useAccounts } from '@/api/accounts'
import { useTeams } from '@/api/teams'
import type { CliId } from '@/api/types'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// Radix Select cannot use "" as an item value.
const NONE = '__none__'

/** «Equipo» of an agent: one of the teams, or none («Sin equipo»). */
export function TeamSelect({
  id,
  value,
  onChange,
}: {
  id?: string
  value: string | null
  onChange: (teamId: string | null) => void
}) {
  const { t } = useTranslation()
  const teams = useTeams().data ?? []
  // A team that was deleted meanwhile reads as none.
  const current = value && teams.some((team) => team.id === value) ? value : NONE
  return (
    <Select value={current} onValueChange={(v) => onChange(v === NONE ? null : v)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{t('teams.none')}</SelectItem>
        {teams.map((team) => (
          <SelectItem key={team.id} value={team.id}>
            {team.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/**
 * «Cuenta» of an agent: one of the logins of its CLI, or the default one. A CLI with a single
 * login (agy keeps one in the system's store) has nothing to choose.
 */
export function AccountSelect({
  id,
  cli,
  value,
  onChange,
}: {
  id?: string
  cli: CliId
  value: string | null
  onChange: (accountId: string | null) => void
}) {
  const { t } = useTranslation()
  const accounts = (useAccounts().data ?? []).filter((a) => a.cli === cli)
  const fallback = accounts.find((a) => a.is_default)
  const current = value && accounts.some((a) => a.id === value) ? value : NONE
  return (
    <Select
      value={current}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
      disabled={accounts.length <= 1}
    >
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>
          {fallback
            ? t('agents.fields.accountDefault', { name: fallback.name })
            : t('agents.fields.accountDefaultNone')}
        </SelectItem>
        {accounts.map((account) => (
          <SelectItem key={account.id} value={account.id}>
            {account.name}
            {account.plan && <span className="text-muted-foreground"> · {account.plan}</span>}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
