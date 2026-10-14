import type { Account, QuotaWindow } from '@/api/types'
import i18n from '@/i18n'
import { formatSeconds } from './format'

/** From this share of a subscription window a notice appears (phase 10). */
export const NEAR_QUOTA = 95

/** From this share a window is painted as «about to run out» (amber), as the daily limit is. */
export const WARN_QUOTA = 80

/** A window the clock has already ended: the CLI's last reading is old news. */
export function isOver(window: QuotaWindow, now: number = Date.now()): boolean {
  return window.expired || now >= new Date(window.resets_at).getTime()
}

/** The windows still open, the most used first. */
export function openWindows(account: Account, now: number = Date.now()): QuotaWindow[] {
  return account.quota.filter((w) => !isOver(w, now)).sort((a, b) => b.used_pct - a.used_pct)
}

/** The most used window of the account that is still open (what the summary shows). */
export function highestWindow(account: Account, now: number = Date.now()): QuotaWindow | undefined {
  return openWindows(account, now)[0]
}

/** «Se reinicia en 1 h 52 min» within a day, «Se reinicia el sáb 17:00» beyond it. */
export function resetsText(window: QuotaWindow, now: number = Date.now()): string {
  const seconds = Math.round((new Date(window.resets_at).getTime() - now) / 1000)
  if (seconds < 24 * 3600)
    return i18n.t('accounts.quota.resetsIn', { time: formatSeconds(Math.max(seconds, 60)) })
  const when = new Intl.DateTimeFormat(i18n.language, {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(window.resets_at))
  return i18n.t('accounts.quota.resetsOn', { when })
}

/** The name of a window as `/usage` of its CLI calls it. */
export function windowName(id: string): string {
  return i18n.t(`accounts.quota.windows.${id}`, { defaultValue: id })
}
