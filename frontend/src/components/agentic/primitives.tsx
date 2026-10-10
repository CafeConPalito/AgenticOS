// Visual primitives from docs/design/code/components/agentic/primitives.tsx, adapted:
// tokens instead of hex where possible and labels passed in (i18n).
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { CliId } from '@/api/types'

export type StatusTone =
  'queued' | 'running' | 'waiting' | 'review' | 'done' | 'failed' | 'cancelled'

const BADGE_SIZE = {
  md: 'h-[22px] px-2 text-[11px]',
  sm: 'h-5 px-[7px] text-[11px]',
  xs: 'h-[19px] px-[7px] text-[10.5px]',
}

/** Tinted pill: text in the status colour, 14% background, 36% border. */
export function StatusBadge({
  tone,
  label,
  size = 'md',
  live = tone === 'running',
  className,
}: {
  tone: StatusTone
  label: string
  size?: keyof typeof BADGE_SIZE
  /** Pulsing dot; by default for `running`. */
  live?: boolean
  className?: string
}) {
  const color = `var(--status-${tone})`
  return (
    <Badge
      variant="outline"
      className={cn(
        'shrink-0 gap-1.5 rounded-full font-medium whitespace-nowrap',
        BADGE_SIZE[size],
        className,
      )}
      style={{
        color,
        background: `color-mix(in oklch, ${color} 14%, transparent)`,
        borderColor: `color-mix(in oklch, ${color} 36%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className={cn('size-1.5 rounded-full bg-current', live && 'animate-live-pulse')}
      />
      {label}
    </Badge>
  )
}

export function AgentAvatar({
  name,
  color,
  label,
  size = 24,
  withTooltip = false,
  className,
}: {
  name: string
  color: string
  /** Accessible name, e.g. "Dev · Desarrollador". */
  label?: string
  size?: number
  withTooltip?: boolean
  className?: string
}) {
  const radius = size <= 16 ? 4 : size <= 24 ? 6 : size <= 34 ? 8 : size <= 48 ? 12 : 14
  const initial = (name.trim()[0] ?? '?').toUpperCase()
  const avatar = (
    <span
      role="img"
      aria-label={label ?? name}
      className={cn(
        'grid shrink-0 place-items-center font-bold text-[#0A1A33] select-none',
        className,
      )}
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        background: color,
        fontSize: Math.round(size * 0.44),
      }}
    >
      {initial}
    </span>
  )
  if (!withTooltip) return avatar
  return (
    <Tooltip>
      <TooltipTrigger asChild>{avatar}</TooltipTrigger>
      <TooltipContent>{label ?? name}</TooltipContent>
    </Tooltip>
  )
}

export function ProjectChip({
  name,
  color,
  variant = 'chip',
}: {
  name: string
  color: string
  variant?: 'chip' | 'dot'
}) {
  if (variant === 'dot')
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <span className="size-2 rounded-[2px]" style={{ background: color }} />
        {name}
      </span>
    )
  return (
    <span
      className="inline-flex h-[18px] items-center gap-1.5 rounded-[5px] px-1.5 text-[11px] text-foreground"
      style={{ background: `color-mix(in oklch, ${color} 16%, transparent)` }}
    >
      <span className="size-1.5 rounded-[2px]" style={{ background: color }} />
      {name}
    </span>
  )
}

const CLI_TAG: Record<CliId, string> = { claude: 'CC', agy: 'AG' }

/** CLI marker («CC», «AG»). To be replaced by official logos following each brand's guidelines. */
export function CliTag({ cli, label, size = 22 }: { cli: CliId; label: string; size?: number }) {
  return (
    <span
      role="img"
      aria-label={label}
      className="grid shrink-0 place-items-center rounded-md border bg-primary font-mono font-bold text-white"
      style={{ width: size, height: size, fontSize: size > 26 ? 11 : 10 }}
    >
      {CLI_TAG[cli]}
    </span>
  )
}
