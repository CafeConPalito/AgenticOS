import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { DailySeries } from '@/api/types'
import { formatTokens, formatUsd, shortDay } from '@/lib/format'

export type Metric = 'cost' | 'tokens'

/**
 * Stacked daily bars, one color per agent or project: the entity's own color, as everywhere in
 * the app. Those colors are chosen by the person, so identity never relies on color alone: the
 * tooltip and the «Reparto del periodo» next to the chart name every series, and segments are
 * separated by a 2px gap.
 */
export function DailyChart({ series, metric }: { series: DailySeries; metric: Metric }) {
  const { t } = useTranslation()
  const format = metric === 'cost' ? formatUsd : formatTokens
  const data = series.days.map((point) => ({
    day: point.day,
    ...Object.fromEntries(
      series.groups.map((g) => [g.id, (metric === 'cost' ? point.cost : point.tokens)[g.id] ?? 0]),
    ),
  }))
  const empty = data.every((row) => series.groups.every((g) => !row[g.id as keyof typeof row]))
  if (empty)
    return (
      <p className="grid h-[200px] place-items-center text-[13px] text-muted-foreground">
        {t('usage.chart.empty')}
      </p>
    )
  const every = Math.max(1, Math.round(data.length / 6))
  return (
    <div className="h-[200px]" data-testid="daily-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
          barCategoryGap="18%"
        >
          <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.6} />
          <XAxis
            dataKey="day"
            tickFormatter={shortDay}
            interval={every - 1}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
          />
          <YAxis
            width={56}
            tickFormatter={(v: number) => format(v)}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
          />
          <Tooltip
            cursor={{ fill: 'var(--accent)', opacity: 0.5 }}
            content={(props) => (
              <DayTooltip
                active={props.active}
                payload={props.payload}
                label={props.label}
                series={series}
                format={format}
              />
            )}
          />
          {series.groups.map((group, i) => (
            <Bar
              key={group.id}
              dataKey={group.id}
              name={group.name}
              stackId="day"
              fill={group.color}
              stroke="var(--card)"
              strokeWidth={2}
              radius={i === series.groups.length - 1 ? [4, 4, 0, 0] : 0}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function DayTooltip({
  active,
  payload,
  label,
  series,
  format,
}: {
  active?: boolean
  payload?: readonly { dataKey?: unknown; value?: unknown }[]
  label?: unknown
  series: DailySeries
  format: (value: number) => string
}) {
  if (!active || !payload?.length) return null
  const rows = series.groups
    .map((g) => ({ ...g, value: Number(payload.find((p) => p.dataKey === g.id)?.value ?? 0) }))
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value)
  const total = rows.reduce((sum, row) => sum + row.value, 0)
  return (
    <div className="min-w-[160px] rounded-lg border bg-popover px-3 py-2 text-[12px] shadow-md">
      <div className="mb-1 flex justify-between gap-4 font-medium">
        <span>{shortDay(String(label))}</span>
        <span className="font-mono">{format(total)}</span>
      </div>
      {rows.map((row) => (
        <div key={row.id} className="flex items-center gap-2 text-muted-foreground">
          <span aria-hidden className="size-2 rounded-[2px]" style={{ background: row.color }} />
          <span className="flex-1 truncate text-foreground">{row.name}</span>
          <span className="font-mono">{format(row.value)}</span>
        </div>
      ))}
    </div>
  )
}
