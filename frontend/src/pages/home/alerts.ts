import type { TFunction } from 'i18next'
import type { CliInfo, InboxItem, InboxKind, UsageToday } from '@/api/types'
import { formatPercent } from '@/lib/format'

/** A CLI notice of Inicio: derived from data that already exists, there is no model for it. */
export interface CliAlert {
  id: string
  title: string
  context: string
  /** The quota/limit request behind it, which keeps its own actions. */
  item?: InboxItem
  createdAt?: string
}

/** From this share of the daily limit a notice appears (at 100 % the `limit` request exists). */
export const NEAR_LIMIT = 0.95

/** Requests painted as a system notice instead of a normal request. */
export const SYSTEM_KINDS: InboxKind[] = ['quota', 'limit']

/** Requests the person answers, most urgent first. */
const REQUEST_ORDER: Partial<Record<InboxKind, number>> = {
  approval: 0,
  question: 1,
  blocker: 2,
  attention: 3,
  stalled: 3,
  review: 4,
  delivery: 5,
}

export function sortRequests(items: InboxItem[]): InboxItem[] {
  return [...items].sort(
    (a, b) =>
      (REQUEST_ORDER[a.kind] ?? 9) - (REQUEST_ORDER[b.kind] ?? 9) ||
      b.created_at.localeCompare(a.created_at),
  )
}

export function buildCliAlerts({
  pending,
  clis,
  today,
  snoozed,
  t,
}: {
  pending: InboxItem[]
  clis: CliInfo[] | undefined
  today: UsageToday | undefined
  snoozed: string[]
  t: TFunction
}): CliAlert[] {
  const alerts: CliAlert[] = []

  for (const item of pending.filter((i) => SYSTEM_KINDS.includes(i.kind))) {
    alerts.push({
      id: `request-${item.id}`,
      title: item.title,
      context: item.detail,
      item,
      createdAt: item.created_at,
    })
  }

  if (Array.isArray(clis)) {
    if (clis.every((cli) => !cli.installed)) {
      alerts.push({
        id: 'cli-missing',
        title: t('cliReadiness.missingTitle'),
        context: t('cliReadiness.missing'),
      })
    }
    for (const cli of clis.filter((c) => c.installed && c.logged_in === false)) {
      alerts.push({
        id: `cli-session-${cli.id}`,
        title: t('home.alerts.loggedOut.title', { cli: t(`cli.${cli.id}`) }),
        context: t('home.alerts.loggedOut.context'),
      })
    }
  }

  const limits = today && Array.isArray(today.limits) ? today.limits : []
  for (const state of limits) {
    if (state.limit === null || state.reached || (state.ratio ?? 0) < NEAR_LIMIT) continue
    alerts.push({
      id: `cli-near-${state.cli}`,
      title: t('home.alerts.nearLimit.title', {
        cli: t(`cli.${state.cli}`),
        percent: formatPercent(state.ratio ?? 0),
      }),
      context: t('home.alerts.nearLimit.context'),
    })
  }

  return alerts.filter((alert) => !snoozed.includes(alert.id))
}
