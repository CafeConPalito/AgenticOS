import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import { TOP_NAV, type TopSection } from './nav'

/** Tablero, Ejecuciones and Ajustes, with their live counters. */
export function TopNav({
  active,
  counts,
}: {
  active: string
  counts: Partial<Record<TopSection, number>>
}) {
  const { t } = useTranslation()
  return (
    <nav aria-label={t('nav.main')} className="flex shrink-0 gap-0.5">
      {TOP_NAV.map(({ id, path }) => {
        const count = counts[id]
        const current = active === id
        return (
          <Link
            key={id}
            to={path}
            aria-current={current ? 'page' : undefined}
            className={cn(
              'flex h-[30px] items-center gap-1.5 rounded-full px-2.5 text-[12.5px] whitespace-nowrap hover:bg-accent hover:text-foreground',
              current ? 'bg-accent text-foreground' : 'text-muted-foreground',
            )}
          >
            {t(`nav.${id}`)}
            {count != null && (
              <span className="font-mono text-[11.5px] text-muted-foreground">{count}</span>
            )}
          </Link>
        )
      })}
    </nav>
  )
}
