import { cn } from '@/lib/utils'

/** The design's segmented control (Tablero, Consumo). */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div role="tablist" aria-label={label} className="flex rounded-lg border bg-subtle p-0.5">
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-md px-3 py-1 text-[13px] text-muted-foreground',
            value === option.value && 'bg-card font-medium text-foreground shadow-sm',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function KpiCard({
  label,
  value,
  hint,
  note,
}: {
  label: string
  value: string
  hint?: string
  note?: string
}) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[12.5px] text-muted-foreground">{label}</span>
        {note && <span className="text-[11px] text-muted-foreground">{note}</span>}
      </div>
      <div className="mt-1.5 font-mono text-[24px] font-medium tracking-[-0.01em]">{value}</div>
      {hint && <div className="mt-1 text-[12px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

/** A thin share bar in the entity's color (reparto, consumo de hoy, límites). */
export function ShareBar({ ratio, color, label }: { ratio: number; color: string; label: string }) {
  const percent = Math.max(0, Math.min(1, ratio)) * 100
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      className="h-1.5 overflow-hidden rounded-full bg-subtle"
    >
      <div className="h-full rounded-full" style={{ width: `${percent}%`, background: color }} />
    </div>
  )
}
