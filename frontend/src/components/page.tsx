import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { AGENT_COLORS } from '@/theme/palettes'

export function PageContainer({
  children,
  narrow = false,
}: {
  children: React.ReactNode
  narrow?: boolean
}) {
  return (
    <div
      className={cn(
        'mx-auto flex flex-col gap-5 px-6 pt-[22px] pb-8',
        narrow ? 'max-w-[1080px]' : 'max-w-[1640px]',
      )}
    >
      {children}
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <h1 className="text-[22px] leading-[1.3] font-medium tracking-[-0.01em]">{title}</h1>
        {subtitle && <p className="mt-1 text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Underlined tabs bound to routes (`/agentes/:id/<tab>`), as in the design. */
export function RouteTabs({
  base,
  tabs,
  label,
}: {
  base: string
  tabs: { id: string; label: string }[]
  label: string
}) {
  return (
    <nav aria-label={label} className="flex gap-1 border-b px-6">
      {tabs.map((tab) => (
        <NavLink
          key={tab.id}
          to={`${base}/${tab.id}`}
          className={({ isActive }) =>
            cn(
              '-mb-px border-b-2 border-transparent px-2.5 py-2.5 text-[13px] text-muted-foreground hover:text-foreground',
              isActive && 'border-primary-action font-medium text-foreground',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}

export function ComingSoonTab({ icon }: { icon: LucideIcon }) {
  const { t } = useTranslation()
  return (
    <div className="px-6 pt-5">
      <EmptyState icon={icon} title={t('common.comingSoonPhase')} />
    </div>
  )
}

export function Field({
  label,
  htmlFor,
  error,
  help,
  children,
  className,
}: {
  label: string
  htmlFor?: string
  error?: string
  help?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <Label htmlFor={htmlFor} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-status-failed">
          {error}
        </p>
      ) : (
        help && <p className="text-xs text-muted-foreground">{help}</p>
      )}
    </div>
  )
}

export const PALETTE = AGENT_COLORS

export function ColorPicker({
  value,
  onChange,
  colorLabel,
}: {
  value: string
  onChange: (color: string) => void
  colorLabel: (color: string) => string
}) {
  return (
    <div role="radiogroup" className="flex flex-wrap gap-2">
      {PALETTE.map((color) => {
        const selected = color.toLowerCase() === value.toLowerCase()
        return (
          <button
            key={color}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={colorLabel(color)}
            onClick={() => onChange(color)}
            className={cn(
              'size-7 rounded-md border-2 border-transparent outline-offset-2',
              selected && 'border-foreground',
            )}
            style={{ background: color }}
          />
        )
      })}
    </div>
  )
}
