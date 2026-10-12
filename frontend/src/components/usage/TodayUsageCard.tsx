import { AlertTriangle, BatteryWarning } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useUsageToday } from '@/api/usage'
import type { LimitState } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { formatPercent, formatTokens, formatUsd } from '@/lib/format'
import { ShareBar } from '@/pages/usage/parts'

const CLI_NAME = { claude: 'Claude Code', agy: 'Antigravity' } as const

function limitValue(state: LimitState, value: number): string {
  return state.unit === 'usd' ? formatUsd(value) : formatTokens(value)
}

/** «Consumo de hoy» (design 01a): tokens, cost, per agent and the daily limits. */
export function TodayUsageCard() {
  const { t } = useTranslation()
  const data = useUsageToday().data
  // Never break the Dashboard over an unexpected answer (e.g. an older backend).
  const today = data && Array.isArray(data.limits) && Array.isArray(data.agents) ? data : undefined
  const claude = today?.limits.find((l) => l.cli === 'claude')
  const maxAgent = Math.max(0, ...(today?.agents ?? []).map((a) => a.cost_usd || a.tokens))
  const byCost = (today?.cost_usd ?? 0) > 0

  return (
    <section
      aria-labelledby="today-usage-title"
      className="flex flex-col gap-4 rounded-xl border bg-card px-4 py-3.5"
    >
      <h2 id="today-usage-title" className="text-[14px] font-medium">
        {t('usage.today.title')}
      </h2>
      {!today ? (
        <Skeleton className="h-40" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[12px] text-muted-foreground">{t('usage.today.tokens')}</div>
              <div className="font-mono text-[22px] font-medium">{formatTokens(today.tokens)}</div>
              <div className="text-[11.5px] text-muted-foreground">
                {t('usage.today.cached', { value: formatTokens(today.cache_read_tokens) })}
              </div>
            </div>
            <div>
              <div className="text-[12px] text-muted-foreground">
                {t('usage.today.cost')}{' '}
                <span className="text-[11px]">· {t('usage.today.costNote')}</span>
              </div>
              <div className="font-mono text-[22px] font-medium">{formatUsd(today.cost_usd)}</div>
              <div className="text-[11.5px] text-muted-foreground">
                {claude?.limit
                  ? t('usage.today.limitOf', { value: formatUsd(claude.limit) })
                  : t('usage.today.noLimit')}
              </div>
            </div>
          </div>

          {today.agents.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">{t('usage.today.empty')}</p>
          ) : (
            <ul aria-label={t('usage.today.byAgent')} className="flex flex-col gap-2">
              {today.agents.map((agent) => {
                const value = byCost ? agent.cost_usd : agent.tokens
                return (
                  <li key={agent.id ?? agent.name} className="flex items-center gap-3 text-[13px]">
                    <span className="w-24 truncate">{agent.name}</span>
                    <div className="flex-1">
                      <ShareBar
                        ratio={maxAgent ? value / maxAgent : 0}
                        color={agent.color}
                        label={agent.name}
                      />
                    </div>
                    <span className="w-16 text-right font-mono text-[12.5px]">
                      {/* agy records no cost: its tokens instead of «0,00 $» */}
                      {byCost && agent.cost_usd > 0
                        ? formatUsd(agent.cost_usd)
                        : formatTokens(agent.tokens)}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}

          {today.limits
            .filter((state) => state.limit !== null || state.quota_exhausted)
            .map((state) => (
              <LimitRow key={state.cli} state={state} />
            ))}

          <Link to="/consumo" className="self-end text-[12.5px] text-ring hover:underline">
            {t('usage.today.detail')}
          </Link>
        </>
      )}
    </section>
  )
}

function LimitRow({ state }: { state: LimitState }) {
  const { t } = useTranslation()
  const cli = CLI_NAME[state.cli]
  const color = state.reached
    ? 'var(--status-failed)'
    : state.near
      ? 'var(--status-waiting)'
      : 'var(--status-done)'
  const percent = formatPercent(state.ratio ?? 0)
  return (
    <div className="flex flex-col gap-1.5">
      {state.limit !== null && (
        <>
          <div className="flex justify-between text-[12px] text-muted-foreground">
            <span>{t('usage.today.limitBar', { cli, percent })}</span>
            <span className="font-mono">
              {limitValue(state, state.used)} / {limitValue(state, state.limit)}
            </span>
          </div>
          <ShareBar
            ratio={state.ratio ?? 0}
            color={color}
            label={t('usage.today.limitBar', { cli, percent })}
          />
        </>
      )}
      {(state.reached || state.near || state.quota_exhausted) && (
        <p
          role="status"
          className="flex items-center gap-1.5 text-[12px]"
          style={{
            color:
              state.reached || state.quota_exhausted
                ? 'var(--status-failed)'
                : 'var(--status-waiting)',
          }}
        >
          {state.quota_exhausted ? (
            <BatteryWarning className="size-3.5" />
          ) : (
            <AlertTriangle className="size-3.5" />
          )}
          {state.quota_exhausted
            ? t('usage.today.quota', { cli })
            : state.reached
              ? t('usage.today.reached', { cli })
              : t('usage.today.near', { cli })}
        </p>
      )}
    </div>
  )
}
