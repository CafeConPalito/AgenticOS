import { Gauge } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { UsageLimits } from '@/api/types'
import { useSaveUsageLimits, useUsageLimits } from '@/api/usage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'

/** «Límites diarios» (phase 07): USD for Claude Code, tokens for Antigravity. */
export function LimitsSection() {
  const limits = useUsageLimits().data
  return limits ? <LimitsForm initial={limits} /> : <Skeleton className="h-48 rounded-xl" />
}

function LimitsForm({ initial }: { initial: UsageLimits }) {
  const { t } = useTranslation()
  const save = useSaveUsageLimits()
  const [claude, setClaude] = useState(
    initial.claude_usd === null ? '' : String(initial.claude_usd),
  )
  const [agy, setAgy] = useState(initial.agy_tokens === null ? '' : String(initial.agy_tokens))

  const parse = (text: string, integer: boolean): number | null | undefined => {
    const clean = text.trim().replace(/\s/g, '').replace(',', '.')
    if (!clean) return null
    const value = integer ? Number(clean.replace(/\./g, '')) : Number(clean)
    return Number.isFinite(value) && value > 0 ? value : undefined
  }
  const claudeValue = parse(claude, false)
  const agyValue = parse(agy, true)
  const invalid = claudeValue === undefined || agyValue === undefined

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (invalid) return
    save.mutate(
      { claude_usd: claudeValue, agy_tokens: agyValue === null ? null : Math.round(agyValue) },
      {
        onSuccess: () => toast.success(t('settings.limits.saved')),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <section
      aria-labelledby="limits-title"
      className="flex flex-col gap-1 rounded-xl border bg-card p-4"
    >
      <h2 id="limits-title" className="flex items-center gap-2 text-[15px] font-medium">
        <Gauge className="size-4" />
        {t('settings.limits.title')}
      </h2>
      <p className="mb-2 text-[13px] text-muted-foreground">{t('settings.limits.description')}</p>
      <form onSubmit={submit} className="flex flex-col">
        {(
          [
            ['claude', claude, setClaude, '$'],
            ['agy', agy, setAgy, 'tokens'],
          ] as const
        ).map(([key, value, setValue, unit]) => (
          <label
            key={key}
            htmlFor={`limit-${key}`}
            className="flex items-center gap-4 border-b py-2.5 last:border-b-0"
          >
            <span className="flex-1">
              <span className="block text-[13.5px] font-medium">{t(`settings.limits.${key}`)}</span>
              <span className="block text-xs text-muted-foreground">
                {t(`settings.limits.${key}Help`)}
              </span>
            </span>
            <span className="flex items-center gap-2">
              <Input
                id={`limit-${key}`}
                inputMode="decimal"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={t('settings.limits.none')}
                className="h-8 w-[140px] text-right font-mono"
              />
              <span className="w-12 text-xs text-muted-foreground">{unit}</span>
            </span>
          </label>
        ))}
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
