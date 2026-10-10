import i18n from '@/i18n'

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
  ['second', 1],
]

/** «hace 2 min», «hace 3 d»… in the UI language. */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000)
  if (Math.abs(seconds) < 10) return i18n.t('time.justNow')
  const format = new Intl.RelativeTimeFormat(i18n.language, { numeric: 'auto', style: 'short' })
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit)
  }
  return format.format(seconds, 'second')
}

/** Elapsed time as «m:ss» or «h:mm:ss» (like the design's session timers). */
export function formatDuration(
  startIso: string | null,
  endIso: string | null,
  now: Date = new Date(),
): string {
  if (!startIso) return '—'
  const end = endIso ? new Date(endIso) : now
  const total = Math.max(0, Math.floor((end.getTime() - new Date(startIso).getTime()) / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/** Date and time for tables: «10/10 12:20», with the year when it is not the current one. */
export function formatDateTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso)
  return new Intl.DateTimeFormat(i18n.language, {
    day: '2-digit',
    month: '2-digit',
    ...(date.getFullYear() !== now.getFullYear() && { year: 'numeric' }),
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
