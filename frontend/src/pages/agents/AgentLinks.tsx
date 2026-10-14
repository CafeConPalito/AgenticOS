import { useTranslation } from 'react-i18next'
import { accountOf, useAccounts } from '@/api/accounts'
import { useClis } from '@/api/clis'
import { useTeams } from '@/api/teams'
import type { CliId } from '@/api/types'
import { Field } from '@/components/page'
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
    // Radix reports an empty value while its items are not mounted yet: ignore it.
    <Select value={current} onValueChange={(v) => v && onChange(v === NONE ? null : v)}>
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
      onValueChange={(v) => v && onChange(v === NONE ? null : v)}
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

const DEFAULT_MODEL = '__default__'

/**
 * «CLI secundario» of an agent: an account (which fixes the CLI) and a model it switches to when
 * its main account is about to run out. Not the main account itself.
 */
export function FallbackFields({
  idPrefix,
  cli,
  accountId,
  fallbackAccountId,
  fallbackModel,
  onChange,
}: {
  idPrefix: string
  cli: CliId
  accountId: string | null
  fallbackAccountId: string | null
  fallbackModel: string
  onChange: (value: { fallback_account_id: string | null; fallback_model: string }) => void
}) {
  const { t } = useTranslation()
  const accounts = useAccounts().data ?? []
  const clis = useClis().data
  const main = accountOf(accounts, { cli, account_id: accountId })
  const options = accounts.filter((a) => a.id !== main?.id)
  const current =
    fallbackAccountId && options.some((a) => a.id === fallbackAccountId) ? fallbackAccountId : NONE
  const selected = options.find((a) => a.id === current)
  const models = clis?.find((c) => c.id === selected?.cli)?.models ?? []
  return (
    <div className="grid grid-cols-2 gap-5">
      <Field
        label={t('agents.fields.fallback')}
        htmlFor={`${idPrefix}-fallback`}
        help={t('agents.fields.fallbackHelp')}
      >
        <Select
          value={current}
          onValueChange={(v) =>
            v &&
            onChange({
              fallback_account_id: v === NONE ? null : v,
              // The model belongs to the CLI: a new account starts with its default.
              fallback_model: '',
            })
          }
        >
          <SelectTrigger id={`${idPrefix}-fallback`} className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>{t('agents.fields.fallbackNone')}</SelectItem>
            {options.map((account) => (
              <SelectItem key={account.id} value={account.id}>
                {t(`cli.${account.cli}`)} · {account.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      {selected && (
        <Field label={t('agents.fields.fallbackModel')} htmlFor={`${idPrefix}-fallback-model`}>
          <Select
            value={fallbackModel || DEFAULT_MODEL}
            onValueChange={(v) =>
              onChange({
                fallback_account_id: selected.id,
                fallback_model: v === DEFAULT_MODEL ? '' : v,
              })
            }
          >
            <SelectTrigger
              id={`${idPrefix}-fallback-model`}
              className="w-full font-mono text-[12.5px]"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_MODEL}>{t('cli.defaultModel')}</SelectItem>
              {fallbackModel && !models.some((m) => m.id === fallbackModel) && (
                <SelectItem value={fallbackModel}>{fallbackModel}</SelectItem>
              )}
              {models.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  <span className="font-mono">{m.id}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}
    </div>
  )
}
