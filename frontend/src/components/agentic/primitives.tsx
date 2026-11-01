// Visual primitives from docs/design/code/components/agentic/primitives.tsx, adapted:
// tokens instead of hex where possible and labels passed in (i18n).
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { avatarSource, useAgentAvatar, useApiBase, useProjectAvatar } from '@/lib/avatars'
import { cn } from '@/lib/utils'
import { readableOn } from '@/theme/contrast'

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

/**
 * An agent's picture on its color (phase 20): an owl of the gallery, its cropped photo or,
 * by default, its initial. Pass `avatar` when the agent is at hand; with only `agentId` it is
 * read from the agents list (runs, tasks and the Inbox carry the name and color, not the
 * picture).
 */
export function AgentAvatar({
  name,
  color,
  avatar,
  agentId,
  label,
  size = 24,
  withTooltip = false,
  className,
}: {
  name: string
  color: string
  avatar?: string | null
  agentId?: string | null
  /** Accessible name, e.g. "Dev · Desarrollador". */
  label?: string
  size?: number
  withTooltip?: boolean
  className?: string
}) {
  const looked = useAgentAvatar(avatar === undefined ? agentId : null)
  const source = avatarSource(avatar === undefined ? looked : avatar, useApiBase())
  // A picture that does not load (a deleted photo, the backend away) falls back to the initial.
  const [broken, setBroken] = useState<string | null>(null)
  const radius = size <= 16 ? 4 : size <= 24 ? 6 : size <= 34 ? 8 : size <= 48 ? 12 : 14
  const initial = (name.trim()[0] ?? '?').toUpperCase()
  const picture = source && source !== broken ? source : null
  const avatarNode = (
    <span
      role="img"
      aria-label={label ?? name}
      className={cn(
        'grid shrink-0 place-items-center overflow-hidden font-bold select-none',
        className,
      )}
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        background: color,
        // Phase 20: dark ink or white, whichever reads on the agent's color.
        color: readableOn(color),
        fontSize: Math.round(size * 0.44),
      }}
    >
      {picture ? (
        <img
          src={picture}
          alt=""
          draggable={false}
          onError={() => setBroken(picture)}
          className="size-full object-cover"
        />
      ) : (
        initial
      )}
    </span>
  )
  if (!withTooltip) return avatarNode
  return (
    <Tooltip>
      <TooltipTrigger asChild>{avatarNode}</TooltipTrigger>
      <TooltipContent>{label ?? name}</TooltipContent>
    </Tooltip>
  )
}

/**
 * The mark of a project (phase 24): its photo, or its color — a small square in lists and
 * chips, its initial on the color from 24 px up. `projectId` looks the photo up in the
 * projects list when the caller only has the name and color; `src` shows a crop that is not
 * uploaded yet.
 */
export function ProjectMark({
  name,
  color,
  avatar,
  projectId,
  src,
  size = 8,
  className,
}: {
  name: string
  color: string
  avatar?: string | null
  projectId?: string | null
  src?: string | null
  size?: number
  className?: string
}) {
  const looked = useProjectAvatar(avatar === undefined ? projectId : null)
  const stored = avatarSource(avatar === undefined ? looked : avatar, useApiBase())
  const [broken, setBroken] = useState<string | null>(null)
  const source = src ?? stored
  const picture = source && source !== broken ? source : null
  const big = size >= 24
  // A photo needs some room to be told apart: never under 14 px.
  const side = picture ? Math.max(size, 14) : size
  const radius = side <= 10 ? 2 : side <= 16 ? 4 : side <= 34 ? 8 : 12
  return (
    <span
      role={big ? 'img' : undefined}
      aria-label={big ? name : undefined}
      aria-hidden={big ? undefined : true}
      data-testid="project-mark"
      className={cn(
        'grid shrink-0 place-items-center overflow-hidden font-bold select-none',
        className,
      )}
      style={{
        width: side,
        height: side,
        borderRadius: radius,
        background: color,
        color: readableOn(color),
        fontSize: Math.round(side * 0.44),
      }}
    >
      {picture ? (
        <img
          src={picture}
          alt=""
          draggable={false}
          onError={() => setBroken(picture)}
          className="size-full object-cover"
        />
      ) : big ? (
        (name.trim()[0] ?? '?').toUpperCase()
      ) : null}
    </span>
  )
}

export function ProjectChip({
  name,
  color,
  projectId,
  variant = 'chip',
}: {
  name: string
  color: string
  /** Phase 24: to show the project's photo instead of its color. */
  projectId?: string | null
  variant?: 'chip' | 'dot'
}) {
  if (variant === 'dot')
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <ProjectMark name={name} color={color} projectId={projectId} />
        {name}
      </span>
    )
  return (
    <span
      className="inline-flex h-[18px] items-center gap-1.5 rounded-[5px] px-1.5 text-[11px] text-foreground"
      style={{ background: `color-mix(in oklch, ${color} 16%, transparent)` }}
    >
      <ProjectMark name={name} color={color} projectId={projectId} size={6} />
      {name}
    </span>
  )
}

/** The two-letter tag of a CLI («CC», «AG»). */
