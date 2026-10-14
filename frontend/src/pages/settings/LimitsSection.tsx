import { Gauge } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { LimitState } from '@/api/types'
import { useSaveUsageLimits, useUsageLimits } from '@/api/usage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'

/** «Límites diarios» (phases 07 and 10): one per account, USD for Claude Code, tokens for agy. */
export function LimitsSection() {
  const limits = useUsageLimits().data
  return Array.isArray(limits) ? (
    <LimitsForm initial={limits} />
  ) : (
    <Skeleton className="h-48 rounded-xl" />
  )
}

const asText = (limit: number | null) => (limit === null ? '' : String(limit))

function LimitsForm({ initial }: { initial: LimitState[] }) {
  const { t } = useTranslation()
  const save = useSaveUsageLimits()
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(initial.map((s) => [s.account_id, asText(s.limit)])),
  )

  const parse = (text: string, integer: boolean): number | null | undefined => {
    const clean = text.trim().replace(/\s/g, '').replace(',', '.')
    if (!clean) return null
    const value = integer ? Number(clean.replace(/\./g, '')) : Number(clean)
    return Number.isFinite(value) && value > 0 ? value : undefined
  }
  const parsed = initial.map((s) => parse(values[s.account_id] ?? '', s.unit === 'tokens'))
  const invalid = parsed.some((value) => value === undefined)
  const several = (cli: string) => initial.filter((s) => s.cli === cli).length > 1

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (invalid) return
    save.mutate(
      initial.map((s, i) => ({
        account_id: s.account_id,
        daily_limit: parsed[i] === null ? null : Math.round((parsed[i] as number) * 100) / 100,
      })),
      {
        onSuccess: () => toast.success(t('settings.limits.saved')),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <section
      aria-labelledby="limits-title"
      className="flex flex-col gap-1 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="limits-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Gauge className="size-4" />
        {t('settings.limits.title')}
      </h2>
      <p className="mb-2 text-[13px] text-muted-foreground">{t('settings.limits.description')}</p>
      <form onSubmit={submit} className="flex flex-col">
        {initial.map((state) => {
          const cliName = t(`cli.${state.cli}`)
          // With a single account the CLI's name is enough; with several, which one it is.
          const label = several(state.cli) ? `${cliName} · ${state.account_name}` : cliName
          return (
            <label
              key={state.account_id}
              htmlFor={`limit-${state.account_id}`}
              className="flex items-center gap-4 border-b py-2.5 last:border-b-0"
            >
              <span className="flex-1">
                <span className="block text-[13.5px] font-medium">
                  {t(`settings.limits.row.${state.unit}`, { name: label })}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {t(`settings.limits.help.${state.unit}`)}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <Input
                  id={`limit-${state.account_id}`}
                  inputMode="decimal"
                  value={values[state.account_id] ?? ''}
                  onChange={(e) => setValues((v) => ({ ...v, [state.account_id]: e.target.value }))}
                  placeholder={t('settings.limits.none')}
                  className="h-8 w-[140px] text-right font-mono"
                />
                <span className="w-12 text-xs text-muted-foreground">
                  {state.unit === 'usd' ? '$' : 'tokens'}
                </span>
              </span>
            </label>
          )
        })}
        {invalid && (
          <p role="alert" className="pt-2 text-[12.5px] text-status-failed">
            {t('settings.limits.invalid')}
          </p>
        )}
        <div className="pt-3">
          <Button
            type="submit"
            size="sm"
            disabled={invalid || save.isPending}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('settings.limits.save')}
          </Button>
        </div>
      </form>
    </section>
  )
}
