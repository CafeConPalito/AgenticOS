import type { LucideIcon } from 'lucide-react'

export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon
  title: string
  description?: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3.5 rounded-lg border border-dashed border-input bg-subtle px-6 py-12 text-center">
      <div className="grid size-11 place-items-center rounded-lg bg-accent">
        <Icon className="size-[22px]" />
      </div>
      <div>
        <div className="text-base font-medium">{title}</div>
        {description && <div className="mt-1 text-pretty text-muted-foreground">{description}</div>}
      </div>
      {children}
    </div>
  )
}
