import { saveFile } from '@/lib/save-file'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, getApiBaseUrl } from '@/lib/api'
import { isoDay } from '@/lib/format'
import { taskKeys } from './tasks'
import type {
  AccountLimit,
  Breakdown,
  DailySeries,
  LimitState,
  SessionRow,
  UsageSummary,
  UsageToday,
} from './types'

export type PeriodDays = 7 | 30 | 90
export type SessionSort =
  'started_at' | 'agent' | 'project' | 'task' | 'model' | 'tokens' | 'cost' | 'duration'

export interface UsageFilters {
  days: PeriodDays
  agentId?: string
  projectId?: string
  accountId?: string
}

export const usageKeys = {
  all: ['usage'] as const,
  summary: (f: UsageFilters) => ['usage', 'summary', f] as const,
  daily: (f: UsageFilters, group: string) => ['usage', 'daily', f, group] as const,
  breakdown: (f: UsageFilters, group: string) => ['usage', 'breakdown', f, group] as const,
  sessions: (f: UsageFilters, sort: SessionSort, dir: 'asc' | 'desc') =>
    ['usage', 'sessions', f, sort, dir] as const,
  today: ['usage', 'today'] as const,
  limits: ['settings', 'usage-limits'] as const,
  threshold: ['settings', 'switch-threshold'] as const,
}

export const PERIODS: PeriodDays[] = [7, 30, 90]

/** The period in the Consumo page's URL (`?periodo=7`), 30 days by default. */
export function periodFromParam(value: string | null): PeriodDays {
  const days = Number(value)
  return PERIODS.includes(days as PeriodDays) ? (days as PeriodDays) : 30
}

const LIVE_MS = 10_000 // usage moves at the end of every turn

/** Query string of a period that ends today (local days). */
export function periodQuery(f: UsageFilters, extra: Record<string, string> = {}): string {
  const to = new Date()
  const from = new Date(to)
  from.setDate(to.getDate() - (f.days - 1))
  const params = new URLSearchParams({ from: isoDay(from), to: isoDay(to), ...extra })
  if (f.agentId) params.set('agent_id', f.agentId)
  if (f.projectId) params.set('project_id', f.projectId)
  if (f.accountId) params.set('account_id', f.accountId)
  return params.toString()
}

export function useUsageSummary(f: UsageFilters) {
  return useQuery({
    queryKey: usageKeys.summary(f),
    queryFn: () => api.get<UsageSummary>(`/api/usage/summary?${periodQuery(f)}`),
    refetchInterval: LIVE_MS,
    placeholderData: keepPreviousData, // no flicker when the period or the order changes
  })
}

export function useUsageDaily(f: UsageFilters, group: 'agent' | 'project' | 'account') {
  return useQuery({
    queryKey: usageKeys.daily(f, group),
    queryFn: () => api.get<DailySeries>(`/api/usage/daily?${periodQuery(f, { group })}`),
    refetchInterval: LIVE_MS,
    placeholderData: keepPreviousData, // no flicker when the period or the order changes
  })
}

export function useUsageBreakdown(
  f: UsageFilters,
  group: 'agent' | 'project' | 'task' | 'account',
  enabled = true,
) {
  return useQuery({
    queryKey: usageKeys.breakdown(f, group),
    queryFn: () => api.get<Breakdown>(`/api/usage/breakdown?${periodQuery(f, { group })}`),
    refetchInterval: LIVE_MS,
    placeholderData: keepPreviousData, // no flicker when the period or the order changes
    enabled,
  })
}

export function useUsageSessions(f: UsageFilters, sort: SessionSort, dir: 'asc' | 'desc') {
  return useQuery({
    queryKey: usageKeys.sessions(f, sort, dir),
    queryFn: () => api.get<SessionRow[]>(`/api/usage/sessions?${periodQuery(f, { sort, dir })}`),
    refetchInterval: LIVE_MS,
    placeholderData: keepPreviousData, // no flicker when the period or the order changes
  })
}

export function useUsageToday() {
  return useQuery({
    queryKey: usageKeys.today,
    queryFn: () => api.get<UsageToday>('/api/usage/today'),
    refetchInterval: LIVE_MS,
  })
}

/** «Consumo del mes»: the breakdown since the 1st of this month. */
export function useMonthBreakdown(group: 'agent' | 'project') {
  const to = new Date()
  const from = new Date(to.getFullYear(), to.getMonth(), 1)
  const query = new URLSearchParams({ from: isoDay(from), to: isoDay(to), group }).toString()
  return useQuery({
    queryKey: ['usage', 'month', group, query] as const,
    queryFn: () => api.get<Breakdown>(`/api/usage/breakdown?${query}`),
    refetchInterval: 60_000,
  })
}

/** The daily limit of each account, with how far it is today. */
export function useUsageLimits() {
  return useQuery({
    queryKey: usageKeys.limits,
    queryFn: () => api.get<LimitState[]>('/api/settings/usage-limits'),
  })
}

/** The percent of a subscription window at which an agent with a secondary CLI asks. */
export function useSwitchThreshold() {
  return useQuery({
    queryKey: usageKeys.threshold,
    queryFn: () => api.get<{ threshold: number }>('/api/settings/switch-threshold'),
  })
}

export function useSaveSwitchThreshold() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (threshold: number) =>
      api.put<{ threshold: number }>('/api/settings/switch-threshold', { threshold }),
    onSuccess: (value) => {
      queryClient.setQueryData(usageKeys.threshold, value)
      return queryClient.invalidateQueries({ queryKey: ['inbox'] })
    },
  })
}

export function useSaveUsageLimits() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limits: AccountLimit[]) =>
      api.put<LimitState[]>('/api/settings/usage-limits', { limits }),
    onSuccess: (limits) => {
      queryClient.setQueryData(usageKeys.limits, limits)
      void queryClient.invalidateQueries({ queryKey: usageKeys.all })
      void queryClient.invalidateQueries({ queryKey: ['inbox'] })
      return queryClient.invalidateQueries({ queryKey: taskKeys.all })
    },
  })
}

/** Saves the sessions of the period as CSV: the path, null if cancelled (see `saveFile`). */
export async function downloadSessionsCsv(f: UsageFilters): Promise<string | null | undefined> {
  const base = await getApiBaseUrl()
  const response = await fetch(`${base}/api/usage/sessions.csv?${periodQuery(f)}`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const disposition = response.headers.get('content-disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'consumo.csv'
  return saveFile({
    name,
    text: await response.text(),
    type: 'text/csv',
    filter: 'CSV',
    extensions: ['csv'],
  })
}
