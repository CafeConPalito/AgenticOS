import i18n from '@/i18n'
import type { UsageTotals } from '@/api/types'

/** «1,33 M», «230,3 k», «950»: tokens abbreviated as in the design. */
export function formatTokens(value: number): string {
  const number = (n: number, digits: number) =>
    new Intl.NumberFormat(i18n.language, {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    }).format(n)
  if (Math.abs(value) >= 1_000_000) return `${number(value / 1_000_000, 2)} M`
  if (Math.abs(value) >= 1_000) return `${number(value / 1_000, 1)} k`
  return number(value, 0)
}

/** «1,8 GB», «230 MB», «12 kB», «0 B»: sizes on disk. */
export function formatBytes(value: number): string {
  const units = ['B', 'kB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1000 && unit < units.length - 1) {
    size /= 1000
    unit += 1
  }
  const digits = unit === 0 || size >= 100 ? 0 : 1
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: digits }).format(
    size,
  )
  return `${number} ${units[unit]}`
}

/** «2,84 $»; «—» without a cost (agy only records tokens). Tiny amounts keep 4 decimals. */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const digits = value !== 0 && Math.abs(value) < 0.01 ? 4 : 2
  return new Intl.NumberFormat(i18n.language, {
    style: 'currency',
    currency: 'USD',
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

/** «26 %»; «+12 %» with `signed`. */
export function formatPercent(ratio: number, signed = false): string {
  return new Intl.NumberFormat(i18n.language, {
    style: 'percent',
    maximumFractionDigits: 0,
    ...(signed && { signDisplay: 'exceptZero' }),
  }).format(ratio)
}

/** «1 h 05 min», «13 min», «40 s». */
export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const total = Math.round(seconds)
  if (total < 60) return `${total} s`
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  return h > 0 ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`
}

/** Every token of a usage block (Claude's output already includes its thinking). */
export function totalTokens(usage: UsageTotals, cli?: string): number {
  return (
    usage.input_tokens +
    usage.output_tokens +
    (cli === 'claude' ? 0 : usage.thinking_tokens) +
    usage.cache_read_tokens +
    usage.cache_creation_tokens
  )
}

/** A local date as `YYYY-MM-DD` (the API's periods are local days). */
export function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** «8 oct» from `YYYY-MM-DD`. */
export function shortDay(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Intl.DateTimeFormat(i18n.language, { day: 'numeric', month: 'short' })
    .format(new Date(y, m - 1, d))
    .replace('.', '')
}
