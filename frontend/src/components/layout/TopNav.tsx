import { CirclePlay, Settings, SquareKanban, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import { TOP_NAV, type TopSection } from './nav'

const ICONS: Record<TopSection, LucideIcon> = {
  board: SquareKanban,
  runs: CirclePlay,
  settings: Settings,
}

/** Tablero, Ejecuciones and Ajustes as icons (phase 23), like the Inbox's. A live counter
 * goes inside the same pill as its icon, so it reads as one. The name is in the tooltip and
 * for screen readers. */
export function TopNav({
  active,
  counts,
}: {
  active: string
  counts: Partial<Record<TopSection, number>>
}) {
  const { t } = useTranslation()
  return (
    <nav aria-label={t('nav.main')} className="flex shrink-0 gap-1">
      {TOP_NAV.map(({ id, path }) => {
        const count = counts[id]
        const current = active === id
        const Icon = ICONS[id]
        return (
          <Link
            key={id}
            to={path}
            title={t(`nav.${id}`)}
            aria-current={current ? 'page' : undefined}
            className={cn(
              'flex h-8 shrink-0 items-center justify-center rounded-full text-foreground hover:bg-accent',
              count != null ? 'gap-1.5 bg-muted/70 pr-2.5 pl-2' : 'w-8',
              current && 'bg-accent',
            )}
          >
            <Icon aria-hidden className="size-[15px]" />
            <span className="sr-only">{t(`nav.${id}`)}</span>
            {count != null && (
              <span className="font-mono text-[11.5px] font-semibold">{count}</span>
            )}
          </Link>
        )
      })}
    </nav>
  )
}
