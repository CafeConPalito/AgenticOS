import { useId } from 'react'
import type { CliId } from '@/api/types'
import { CLI_COLORS } from '@/theme/palettes'

/**
 * The icon of a CLI (phase 23, ADR 0029): drawn by the app, neutral, recognisable by the color
 * the CLI goes with and a simple symbol. Not their logos, which are registered trademarks, and
 * no shape copied from them. A CLI without an icon of its own gets a plain terminal one.
 */
export function CliIcon({
  cli,
  label,
  size = 22,
  className,
}: {
  cli: CliId | string
  label: string
  size?: number
  className?: string
}) {
  const gradient = useId()
  const colors = CLI_COLORS[cli as CliId] ?? CLI_COLORS.generic
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      style={{ flexShrink: 0 }}
    >
      <title>{label}</title>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={colors.from} />
          <stop offset="1" stopColor={colors.to} />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill={`url(#${gradient})`} />
      <Glyph cli={cli} />
    </svg>
  )
}

function Glyph({ cli }: { cli: CliId | string }) {
  const stroke = {
    fill: 'none',
    stroke: CLI_COLORS.glyph,
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
  } as const
  if (cli === 'claude')
    // A terminal prompt: «>_».
    return (
      <g {...stroke}>
        <path d="M6.5 8.5 10 12l-3.5 3.5" />
        <path d="M12.5 16h5" />
      </g>
    )
  if (cli === 'agy')
    // Antigravity: an arrow rising through an orbit.
    return (
      <g {...stroke}>
        <ellipse cx="12" cy="14.5" rx="7" ry="2.6" strokeWidth={1.6} />
        <path d="M12 18V6.5" />
        <path d="m8.5 9.5 3.5-3.5 3.5 3.5" />
      </g>
    )
  return (
    <g {...stroke}>
      <path d="M7 9l3 3-3 3" />
    </g>
  )
}
