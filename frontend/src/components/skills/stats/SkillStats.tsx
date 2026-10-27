import { ArrowDown, ArrowUp, FileDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useAccounts } from '@/api/accounts'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import {
  type StatsFilters,
  type StatsGroup,
  type StatsRow,
  statsCsvUrl,
  statsQuery,
  useSkillStats,
  useSkillStatsDaily,
  useSkillStatsRuns,
} from '@/api/skills'
import { useTeams } from '@/api/teams'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { formatTokens, formatUsd, shortDay } from '@/lib/format'
import { relativeTime } from '@/lib/time'

const ANY = '-'
const GROUPS: StatsGroup[] = [
  'agent',
  'team',
  'project',
  'pipeline',
  'stage',
  'cli',
  'account',
  'model',
]
const FILTER_KEYS = [
  'agent_id',
  'team_id',
  'project_id',
  'pipeline_id',
  'stage_id',
  'cli',
  'account_id',
  'model',
  'scope',
  'origin',
  'via',
  'unused',
] as const
type FilterKey = (typeof FILTER_KEYS)[number]
type Column =
  | 'name'
  | 'group_label'
  | 'offered'
  | 'loaded'
  | 'rate'
  | 'runs'
  | 'tasks'
  | 'avg_cost'
  | 'avg_tokens'
  | 'last_used'
// The commit graph's lane colors: distinct on light and dark, and they follow the theme.
const PALETTE = [0, 1, 2, 3, 4, 5].map((i) => `var(--graph-${i})`)

function periodBounds(period: string): { from?: string; to?: string } {
  if (period === 'all') return {}
  const days = period === 'today' ? 0 : period === '7d' ? 6 : 29
  const day = (d: Date) => d.toLocaleDateString('sv-SE') // YYYY-MM-DD, local
  const to = new Date()
  const from = new Date()
  from.setDate(to.getDate() - days)
  return { from: day(from), to: day(to) }
}

/** The options of one filter: names from the app, or the values seen in the figures. */
function useOptions(key: FilterKey, seen: Record<string, [string, string][]>) {
  const { t } = useTranslation()
  const agents = useAgents().data ?? []
  const teams = useTeams().data ?? []
  const projects = useProjects().data ?? []
  const accounts = useAccounts().data ?? []
  switch (key) {
    case 'agent_id':
      return agents.map((a) => [a.id, a.name] as [string, string])
    case 'team_id':
      return teams.map((x) => [x.id, x.name] as [string, string])
    case 'project_id':
      return projects.map((p) => [p.id, p.name] as [string, string])
    case 'account_id':
      return accounts.map((a) => [a.id, a.label] as [string, string])
    case 'cli':
      return [
        ['claude', t('cli.claude')],
        ['agy', t('cli.agy')],
      ] as [string, string][]
    case 'scope':
      return (['general', 'project', 'agent'] as const).map(
        (s) => [s, t(`skills.level.${s}`)] as [string, string],
      )
    case 'origin':
      return (['user', 'agent', 'import', 'registry'] as const).map(
        (o) =>
          [o, t(`skills.origin.${o === 'registry' ? 'registry_short' : o}`)] as [string, string],
      )
    case 'via':
      return (['context', 'tool', 'native'] as const).map(
        (v) => [v, t(`skills.run.via.${v}`)] as [string, string],
      )
    case 'unused':
      return (['never_loaded', 'never_offered'] as const).map(
        (u) => [u, t(`skills.stats.unused.${u}`)] as [string, string],
      )
    default:
      return seen[key] ?? []
  }
}

function FilterSelect({
  name,
  value,
  onChange,
  seen,
}: {
  name: FilterKey
  value: string | undefined
  onChange: (value: string | undefined) => void
  seen: Record<string, [string, string][]>
}) {
  const { t } = useTranslation()
  const options = useOptions(name, seen)
  if (options.length === 0 && !value) return null
  return (
    <Select value={value ?? ANY} onValueChange={(v) => onChange(v === ANY ? undefined : v)}>
      <SelectTrigger aria-label={t(`skills.stats.filters.${name}`)} className="h-8 w-[150px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY}>
          {t(`skills.stats.filters.${name}`)}: {t('skills.stats.filters.any')}
        </SelectItem>
        {options.map(([id, label]) => (
          <SelectItem key={id} value={id}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/**
 * «Uso» (spec E): which skills are used most, where and with what result. In the page the
 * filters live in the URL; in a skill's sheet (`skillId`, `compact`) they are local.
 */
export function SkillStats({ skillId, compact = false }: { skillId?: string; compact?: boolean }) {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const [local, setLocal] = useState<Record<string, string>>({})
  const read = (key: string) => (compact ? local[key] : (params.get(`u_${key}`) ?? undefined))
  // Several keys at once: two writes in a row would each start from the same old address.
  const writeAll = (updates: Record<string, string | undefined>) => {
    if (compact) {
      setLocal((current) => {
        const next = { ...current }
        for (const [key, value] of Object.entries(updates)) {
          if (value) next[key] = value
          else delete next[key]
        }
        return next
      })
      return
    }
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const [key, value] of Object.entries(updates)) {
          if (value) next.set(`u_${key}`, value)
          else next.delete(`u_${key}`)
        }
        return next
      },
      { replace: true },
    )
  }
  const write = (key: string, value: string | undefined) => writeAll({ [key]: value })
  const period = read('period') ?? 'all'
  const group = (read('group') as StatsGroup | undefined) ?? (compact ? 'agent' : undefined)
  const sort = (read('sort') as Column | undefined) ?? 'loaded'
  const desc = read('desc') !== 'false'
  const filters: StatsFilters = {
    ...periodBounds(period),
    ...Object.fromEntries(FILTER_KEYS.map((k) => [k, read(k)]).filter(([, v]) => v)),
    ...(skillId ? { skill_id: skillId } : {}),
  }
  const query = statsQuery(filters, { group_by: group, sort, desc: desc ? 'true' : 'false' })
  const stats = useSkillStats(query)
  // The values a filter can take that the app has no list of (pipelines, stages, models).
  const seenQuery = (by: StatsGroup) => statsQuery({ ...periodBounds(period) }, { group_by: by })
  const pipelines = useSkillStats(seenQuery('pipeline'))
  const models = useSkillStats(seenQuery('model'))
  const seen = useMemo(() => {
    const pairs = (rows: StatsRow[] | undefined) => {
      const map = new Map<string, string>()
      for (const row of rows ?? [])
        if (row.group_key) map.set(row.group_key, row.group_label || row.group_key)
      return [...map.entries()]
    }
    return {
      pipeline_id: pairs(pipelines.data?.rows),
      model: pairs(models.data?.rows),
    }
  }, [pipelines.data, models.data])
  const [picked, setPicked] = useState<string[]>([])
  const daily = useSkillStatsDaily(
    statsQuery(filters, { skill_ids: (skillId ? [skillId] : picked).join(',') }),
    !!skillId || picked.length > 0,
  )
  const [runsOf, setRunsOf] = useState<{ row: StatsRow; query: string } | null>(null)
  const rows = stats.data?.rows ?? []

  function sortBy(column: Column) {
    if (column === sort) write('desc', desc ? 'false' : undefined)
    else
      writeAll({
        sort: column === 'loaded' ? undefined : column,
        desc: column === 'name' || column === 'group_label' ? 'false' : undefined,
      })
  }

  const header = (column: Column) => (
    <th
      scope="col"
      aria-sort={sort === column ? (desc ? 'descending' : 'ascending') : undefined}
      className="px-2 py-1.5 text-left font-medium whitespace-nowrap"
    >
      <button
        type="button"
        onClick={() => sortBy(column)}
        aria-label={t('skills.stats.sort', { column: t(`skills.stats.columns.${column}`) })}
        className="inline-flex items-center gap-1"
      >
        {t(`skills.stats.columns.${column}`)}
        {sort === column &&
          (desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </th>
  )

  const top = [...rows]
    .filter((r) => r.loaded > 0)
    .sort((a, b) => b.loaded - a.loaded)
    .slice(0, 10)
    .map((r) => ({ name: group ? `${r.name} · ${r.group_label}` : r.name, loaded: r.loaded }))
  const series = skillId ? [skillId] : picked
  const names = Object.fromEntries(rows.map((r) => [r.skill_id, r.name]))

  return (
    <div className={compact ? 'flex flex-col gap-3' : 'flex flex-col gap-4 px-6 pt-5 pb-8'}>
      {!compact && (
        <div>
          <h2 className="text-[16px] font-medium">{t('skills.stats.title')}</h2>
          <p className="text-[13px] text-muted-foreground">{t('skills.stats.hint')}</p>
        </div>
      )}
      <div role="group" aria-label={t('skills.stats.period')} className="flex flex-wrap gap-1.5">
        {(['today', '7d', '30d', 'all'] as const).map((p) => (
          <Button
            key={p}
            type="button"
            size="sm"
            variant="outline"
            aria-pressed={period === p}
            className={period === p ? 'border-ring bg-accent' : ''}
            onClick={() => write('period', p === 'all' ? undefined : p)}
          >
            {t(`skills.stats.periods.${p}`)}
          </Button>
        ))}
      </div>
      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          {FILTER_KEYS.filter((k) => k !== 'stage_id').map((key) => (
            <FilterSelect
              key={key}
              name={key}
              value={read(key)}
              onChange={(v) => write(key, v)}
              seen={seen}
            />
          ))}
          {FILTER_KEYS.some((k) => read(k)) && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => writeAll(Object.fromEntries(FILTER_KEYS.map((k) => [k, undefined])))}
            >
              {t('skills.stats.filters.clear')}
            </Button>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={group ?? ANY}
          onValueChange={(v) => write('group', v === ANY ? undefined : v)}
        >
          <SelectTrigger aria-label={t('skills.stats.groupBy')} className="h-8 w-[200px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {!compact && <SelectItem value={ANY}>{t('skills.stats.noGroup')}</SelectItem>}
            {GROUPS.map((g) => (
              <SelectItem key={g} value={g}>
                {t('skills.stats.groupBy')}: {t(`skills.stats.groups.${g}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!compact && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="ml-auto"
            onClick={async () =>
              window.open(await statsCsvUrl(statsQuery(filters, { group_by: group })), '_blank')
            }
          >
            <FileDown />
            {t('skills.stats.export')}
          </Button>
        )}
      </div>
      {stats.isPending ? (
        <Skeleton aria-busy className="h-32 rounded-lg" />
      ) : rows.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">{t('skills.stats.empty')}</p>
      ) : (
        <>
          <div className="overflow-auto rounded-lg border border-sep">
            <table className="w-full border-collapse text-[12.5px]">
              <thead className="bg-subtle">
                <tr>
                  {!compact && <th className="w-8" />}
                  {!skillId && header('name')}
                  {group && header('group_label')}
                  {header('offered')}
                  {header('loaded')}
                  {header('rate')}
                  {header('runs')}
                  {header('tasks')}
                  <th scope="col" className="px-2 py-1.5 text-left font-medium">
                    {t('skills.stats.columns.result')}
                  </th>
                  {header('avg_cost')}
                  {header('avg_tokens')}
                  {header('last_used')}
                  <th scope="col" className="px-2 py-1.5 text-left font-medium">
                    {t('skills.stats.columns.via')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={`${row.skill_id}:${row.group_key ?? ''}`}
                    className="border-t border-sep"
                  >
                    {!compact && (
                      <td className="px-2 text-center">
                        <input
                          type="checkbox"
                          aria-label={t('skills.stats.pick', { name: row.name })}
                          checked={picked.includes(row.skill_id)}
                          onChange={(e) =>
                            setPicked((current) =>
                              e.target.checked
                                ? [...new Set([...current, row.skill_id])]
                                : current.filter((id) => id !== row.skill_id),
                            )
                          }
                        />
                      </td>
                    )}
                    {!skillId && <td className="px-2 py-1.5 font-mono">{row.name}</td>}
                    {group && <td className="px-2 py-1.5">{row.group_label || '—'}</td>}
                    <td className="px-2 py-1.5 tabular-nums">{row.offered}</td>
                    <td className="px-2 py-1.5 tabular-nums">
                      <button
                        type="button"
                        className="underline decoration-dotted"
                        aria-label={t('skills.stats.runsFigure', { name: row.name })}
                        onClick={() =>
                          setRunsOf({
                            row,
                            query: statsQuery(
                              { ...filters, skill_id: row.skill_id },
                              { group_by: group, group_key: row.group_key ?? undefined },
                            ),
                          })
                        }
                      >
                        {row.loaded}
                      </button>
                    </td>
                    <td className="px-2 py-1.5 tabular-nums">
                      {row.rate === null ? '—' : `${Math.round(row.rate * 100)} %`}
                    </td>
                    <td className="px-2 py-1.5 tabular-nums">{row.runs}</td>
                    <td className="px-2 py-1.5 tabular-nums">{row.tasks}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap text-muted-foreground">
                      {t('skills.stats.result', {
                        done: row.done,
                        failed: row.failed,
                        approved: row.approved,
                        rejected: row.rejected,
                      })}
                    </td>
                    <td className="px-2 py-1.5 tabular-nums">
                      {row.avg_cost === null ? '—' : formatUsd(row.avg_cost)}
                    </td>
                    <td className="px-2 py-1.5 tabular-nums">
                      {row.avg_tokens === null ? '—' : formatTokens(row.avg_tokens)}
                    </td>
                    <td className="px-2 py-1.5 whitespace-nowrap">
                      {row.last_used ? relativeTime(row.last_used) : t('skills.stats.never')}
                    </td>
                    <td className="px-2 py-1.5 whitespace-nowrap text-muted-foreground">
                      {t('skills.stats.viaShort', {
                        inContext: row.via_context,
                        byTool: row.via_tool,
                        byCli: row.via_native,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!compact && top.length > 0 && (
            <section aria-label={t('skills.stats.top')} className="flex flex-col gap-1">
              <h3 className="text-[13px] font-medium">{t('skills.stats.top')}</h3>
              <div className="h-[240px]" data-testid="top-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={top} layout="vertical" margin={{ left: 8, right: 8 }}>
                    <CartesianGrid horizontal={false} stroke="var(--border)" strokeOpacity={0.6} />
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="loaded" fill={PALETTE[0]} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}
          <section aria-label={t('skills.stats.daily')} className="flex flex-col gap-1">
            <h3 className="text-[13px] font-medium">{t('skills.stats.daily')}</h3>
            {series.length === 0 ? (
              <p className="text-[12.5px] text-muted-foreground">{t('skills.stats.dailyPick')}</p>
            ) : (
              <div className="h-[200px]" data-testid="daily-skills-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={(daily.data ?? []).map((d) => ({
                      day: d.day,
                      ...Object.fromEntries(series.map((id) => [id, d.loads[id] ?? 0])),
                    }))}
                  >
                    <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.6} />
                    <XAxis dataKey="day" tickFormatter={shortDay} tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} width={32} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    {series.map((id, i) => (
                      <Line
                        key={id}
                        type="monotone"
                        dataKey={id}
                        name={names[id] ?? id}
                        stroke={PALETTE[i % PALETTE.length]}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>
        </>
      )}
      <RunsSheet target={runsOf} onClose={() => setRunsOf(null)} />
    </div>
  )
}

/** The runs behind one figure, each with the version it used and a link to it. */
function RunsSheet({
  target,
  onClose,
}: {
  target: { row: StatsRow; query: string } | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const runs = useSkillStatsRuns(target?.query ?? null)
  return (
    <Sheet open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-2xl">
        <SheetHeader className="border-b">
          <SheetTitle>
            {target && t('skills.stats.runsTitle', { name: target.row.name })}
          </SheetTitle>
          <SheetDescription>{target?.row.group_label}</SheetDescription>
        </SheetHeader>
        <ul className="flex flex-col gap-1.5 overflow-auto px-4 pb-4 text-[12.5px]">
          {(runs.data ?? []).map((run) => (
            <li
              key={`${run.run_id}:${run.skill_id}`}
              className="rounded-lg border border-sep px-3 py-2"
            >
              <Link to={`/ejecuciones/${run.run_id}`} className="font-medium underline">
                {run.agent_name} · {run.project_name || '—'}
              </Link>
              <span className="text-muted-foreground">
                {' '}
                · {relativeTime(run.started_at)} · {run.stage_name || run.cli} ·{' '}
                {run.version !== null && t('skills.run.version', { number: run.version })}{' '}
                {run.loaded_via ? t(`skills.run.via.${run.loaded_via}`) : t('skills.run.notLoaded')}
              </span>
            </li>
          ))}
        </ul>
      </SheetContent>
    </Sheet>
  )
}
