import type { TFunction } from 'i18next'
import type { Account, CliInfo, InboxItem, InboxKind, UsageToday } from '@/api/types'
import { formatPercent } from '@/lib/format'
import { highestWindow, NEAR_QUOTA, resetsText, windowName } from '@/lib/quota'

/** A CLI notice of Inicio: derived from data that already exists, there is no model for it. */
export interface CliAlert {
  id: string
  title: string
  context: string
  /** The quota/limit/session request behind it, which keeps its own actions. */
  item?: InboxItem
  createdAt?: string
}

/** From this share of the daily limit a notice appears (at 100 % the `limit` request exists). */
export const NEAR_LIMIT = 0.95

/** Requests painted as a system notice instead of a normal request. */
export const SYSTEM_KINDS: InboxKind[] = ['quota', 'limit', 'account']

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

/** «Claude Code», or «Claude Code · marta@…» when the CLI has several accounts. */
export function accountLabel(account: Account, accounts: Account[], t: TFunction): string {
  const cli = t(`cli.${account.cli}`)
  return accounts.filter((a) => a.cli === account.cli).length > 1 ? `${cli} · ${account.name}` : cli
}

export function buildCliAlerts({
  pending,
  clis,
  accounts,
  today,
  snoozed,
  t,
  now = Date.now(),
}: {
  pending: InboxItem[]
  clis: CliInfo[] | undefined
  accounts: Account[] | undefined
  today: UsageToday | undefined
  snoozed: string[]
  t: TFunction
  now?: number
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

  if (Array.isArray(clis) && clis.every((cli) => !cli.installed)) {
    alerts.push({
      id: 'cli-missing',
      title: t('cliReadiness.missingTitle'),
      context: t('cliReadiness.missing'),
    })
  }

  // An account about to use up a subscription window (the CLI's own figures, phase 10). It goes
  // away by itself when the window resets.
  const all = Array.isArray(accounts) ? accounts : []
  for (const account of all) {
    const window = highestWindow(account, now)
    if (!window || window.used_pct < NEAR_QUOTA) continue
    alerts.push({
      id: `quota-near-${account.id}`,
      title: t('home.alerts.quotaNear.title', {
        account: accountLabel(account, all, t),
        window: windowName(window.id),
        percent: Math.round(window.used_pct),
      }),
      context: t('home.alerts.quotaNear.context', { reset: resetsText(window, now) }),
    })
  }

  const limits = today && Array.isArray(today.limits) ? today.limits : []
  for (const state of limits) {
    if (state.limit === null || state.reached || (state.ratio ?? 0) < NEAR_LIMIT) continue
    alerts.push({
      id: `limit-near-${state.account_id}`,
      title: t('home.alerts.nearLimit.title', {
        cli: (() => {
          const account = all.find((a) => a.id === state.account_id)
          return account ? accountLabel(account, all, t) : t(`cli.${state.cli}`)
        })(),
        percent: formatPercent(state.ratio ?? 0),
      }),
      context: t('home.alerts.nearLimit.context'),
    })
  }

  return alerts.filter((alert) => !snoozed.includes(alert.id))
}
