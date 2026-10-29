import { toastSaved } from '@/lib/save-file'
import { ChartColumn, Download } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useAccounts } from '@/api/accounts'
import {
  PERIODS,
  periodFromParam,
  type SessionSort,
  useUsageBreakdown,
  useUsageDaily,
  useUsageSessions,
  downloadSessionsCsv,
  useUsageSummary,
} from '@/api/usage'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/form-errors'
import { formatPercent, formatTokens, formatUsd } from '@/lib/format'
import { DailyChart, type Metric } from './usage/DailyChart'
import { KpiCard, Segmented, ShareBar } from './usage/parts'
import { SessionsTable } from './usage/SessionsTable'

type Group = 'agent' | 'project' | 'account'
const ALL = '__all__' // Radix Select cannot use "" as an item value

const GROUP_PARAM: Record<string, Group> = { proyecto: 'project', cuenta: 'account' }
const PARAM_OF: Record<Group, string | null> = {
  agent: null,
  project: 'proyecto',
  account: 'cuenta',
}
const CHART_TITLE: Record<Group, 'titleAgent' | 'titleProject' | 'titleAccount'> = {
  agent: 'titleAgent',
  project: 'titleProject',
  account: 'titleAccount',
}
const TOKENS_TITLE: Record<
  Group,
  'tokensTitleAgent' | 'tokensTitleProject' | 'tokensTitleAccount'
> = {
  agent: 'tokensTitleAgent',
  project: 'tokensTitleProject',
  account: 'tokensTitleAccount',
}

/** agy records no cost: its rows show tokens instead of «0,00 $». */
const noCost = (row: { cost_usd: number; tokens: number }) => row.cost_usd === 0 && row.tokens > 0

export default function UsagePage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const days = periodFromParam(params.get('periodo'))
  const group: Group = GROUP_PARAM[params.get('agrupar') ?? ''] ?? 'agent'
  const accounts = useAccounts().data ?? []
  // A filter is worth showing once there is something to choose from beyond the system accounts.
  const accountId = accounts.some((a) => a.id === params.get('cuenta'))
    ? (params.get('cuenta') as string)
    : undefined
  const [sort, setSort] = useState<SessionSort>('started_at')
  const [dir, setDir] = useState<'asc' | 'desc'>('desc')
  const filters = { days, accountId }

  const summary = useUsageSummary(filters)
  const daily = useUsageDaily(filters, group)
  const breakdown = useUsageBreakdown(filters, group)
  const sessions = useUsageSessions(filters, sort, dir)

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  function exportCsv() {
    downloadSessionsCsv(filters).then(toastSaved, (error: unknown) =>
      toast.error(errorMessage(error)),
    )
  }

  const kpis = summary.data?.kpis
  // With only agy (no cost) the chart shows tokens instead of an empty cost chart.
  const metric: Metric = kpis && kpis.cost_usd === 0 && kpis.tokens > 0 ? 'tokens' : 'cost'
  const number = (n: number, digits = 1) =>
    new Intl.NumberFormat(i18n.language, { maximumFractionDigits: digits }).format(n)
  const chartTitle = t(
    `usage.chart.${metric === 'cost' ? CHART_TITLE[group] : TOKENS_TITLE[group]}` as const,
  )

  return (
    <PageContainer>
      <PageHeader
        title={t('pages.usage.title')}
        subtitle={t('usage.subtitle')}
        actions={
          <>
            <Segmented
              label={t('usage.period.30')}
              value={days}
              options={PERIODS.map((p) => ({ value: p, label: t(`usage.period.${p}`) }))}
              onChange={(value) => update('periodo', value === 30 ? null : String(value))}
            />
            {accounts.length > 2 && (
              <Select
                value={accountId ?? ALL}
                onValueChange={(value) => update('cuenta', value === ALL ? null : value)}
              >
                <SelectTrigger aria-label={t('usage.filters.account')} className="w-[210px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('usage.filters.allAccounts')}</SelectItem>
                  {accounts.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {t(`cli.${account.cli}`)} · {account.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <Button variant="outline" onClick={exportCsv}>
              <Download />
              {t('header.primary.exportCsv')}
            </Button>
          </>
        }
      />

      <section
        className="grid grid-cols-2 gap-3 xl:grid-cols-4"
        aria-label={t('pages.usage.title')}
      >
        {!kpis ? (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-xl" />)
        ) : (
          <>
            <KpiCard
              label={t('usage.kpis.cost')}
              note={t('usage.kpis.costNote')}
              value={formatUsd(kpis.cost_usd)}
              hint={
                kpis.cost_change === null
                  ? t('usage.kpis.costNoPrevious')
                  : t('usage.kpis.costChange', { value: formatPercent(kpis.cost_change, true) })
              }
            />
            <KpiCard
              label={t('usage.kpis.tokens')}
              value={formatTokens(kpis.tokens)}
              hint={
                kpis.cache_ratio === null
                  ? undefined
                  : t('usage.kpis.cacheShare', { value: formatPercent(kpis.cache_ratio) })
              }
            />
            <KpiCard
              label={t('usage.kpis.hours')}
              value={`${number(kpis.agent_hours, kpis.agent_hours < 1 ? 2 : 1)} h`}
              hint={t('usage.kpis.workdays', { count: Math.round(kpis.agent_hours / 8) })}
            />
            <KpiCard
              label={t('usage.kpis.sessions')}
              value={number(kpis.sessions, 0)}
              hint={
                kpis.success_ratio === null
                  ? undefined
                  : t('usage.kpis.success', { value: formatPercent(kpis.success_ratio) })
              }
            />
          </>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2.2fr)_minmax(260px,1fr)]">
        <section
          className="rounded-xl border border-sep px-4 py-3.5 shadow-card bg-card-grad"
          aria-label={chartTitle}
        >
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-[14px] font-medium">{chartTitle}</h2>
            <Segmented
              label={chartTitle}
              value={group}
              options={[
                { value: 'agent' as const, label: t('usage.chart.byAgent') },
                { value: 'project' as const, label: t('usage.chart.byProject') },
                { value: 'account' as const, label: t('usage.chart.byAccount') },
              ]}
              onChange={(value) => update('agrupar', PARAM_OF[value])}
            />
          </div>
          {daily.data ? (
            <DailyChart series={daily.data} metric={metric} />
          ) : (
            <Skeleton className="h-[200px]" />
          )}
        </section>

        <section className="rounded-xl border border-sep px-4 py-3.5 shadow-card bg-card-grad">
          <h2 className="mb-3 text-[14px] font-medium">{t('usage.breakdown.title')}</h2>
          {breakdown.data && breakdown.data.rows.length === 0 && (
            <p className="text-[13px] text-muted-foreground">{t('usage.breakdown.empty')}</p>
          )}
          <ul className="flex flex-col gap-3">
            {(breakdown.data?.rows ?? []).map((row) => (
              <li key={row.id ?? row.name} className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 text-[13px]">
                  <span
                    aria-hidden
                    className="size-2 rounded-[2px]"
                    style={{ background: row.color }}
                  />
                  <span className="flex-1 truncate font-medium">{row.name}</span>
                  <span className="font-mono">
                    {metric === 'cost' && !noCost(row)
                      ? formatUsd(row.cost_usd)
                      : formatTokens(row.tokens)}
                  </span>
                  <span className="w-10 text-right font-mono text-[12px] text-muted-foreground">
                    {row.share === null || (metric === 'cost' && noCost(row))
                      ? '—'
                      : formatPercent(row.share)}
                  </span>
                </div>
                <ShareBar ratio={row.share ?? 0} color={row.color} label={row.name} />
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="overflow-hidden rounded-xl border border-sep shadow-card bg-card-grad">
        <h2 className="border-b px-4 py-3 text-[14px] font-medium">{t('usage.sessions.title')}</h2>
        {sessions.data && sessions.data.length === 0 ? (
          <EmptyState
            icon={ChartColumn}
            title={t('pages.usage.emptyTitle')}
            description={t('pages.usage.emptyDescription')}
          />
        ) : sessions.data ? (
          <SessionsTable
            rows={sessions.data}
            sort={sort}
            dir={dir}
            onSort={(nextSort, nextDir) => {
              setSort(nextSort)
              setDir(nextDir)
            }}
          />
        ) : (
          <Skeleton className="m-4 h-40" />
        )}
      </section>
    </PageContainer>
  )
}
