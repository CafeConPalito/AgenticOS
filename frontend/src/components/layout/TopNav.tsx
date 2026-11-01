import { CirclePlay, Library, Plug, Settings, SquareKanban, type LucideIcon } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import type { TopSection } from './nav'

type Item = { id: TopSection | 'knowledge' | 'connections'; path: string; Icon: LucideIcon }

const BOARD: Item = { id: 'board', path: '/tablero', Icon: SquareKanban }
const RUNS: Item = { id: 'runs', path: '/ejecuciones', Icon: CirclePlay }
/** Documents and skills are one page, Conocimiento. */
const KNOWLEDGE: Item = { id: 'knowledge', path: '/conocimiento', Icon: Library }
const CONNECTIONS: Item = { id: 'connections', path: '/conexiones', Icon: Plug }
const SETTINGS: Item = { id: 'settings', path: '/ajustes', Icon: Settings }

/** The top bar's icons (phase 23), in groups: the work (Tablero, Ejecuciones, Inbox), what the
 * agents use (Conocimiento, Conexiones) and Ajustes. A live counter goes inside the same pill
 * as its icon, so it reads as one. The name is in the tooltip and for screen readers. */
export function TopNav({
  active,
  counts,
  inbox,
}: {
  active: string
  counts: Partial<Record<TopSection, number>>
  /** The Inbox's link, with its own badge. */
  inbox: ReactNode
}) {
  const { t } = useTranslation()
  const link = ({ id, path, Icon }: Item) => {
    const count = id in counts ? counts[id as TopSection] : undefined
    const label = id === 'knowledge' || id === 'connections' ? t(`header.${id}`) : t(`nav.${id}`)
    return (
      <Link
        key={id}
        to={path}
        title={label}
        aria-current={active === id ? 'page' : undefined}
        className={cn(
          'flex h-8 shrink-0 items-center justify-center rounded-full text-foreground hover:bg-accent',
          count != null ? 'gap-1.5 bg-muted/70 pr-2.5 pl-2' : 'w-8',
          active === id && 'bg-accent',
        )}
      >
        <Icon aria-hidden className="size-[15px]" />
        <span className="sr-only">{label}</span>
        {count != null && <span className="font-mono text-[11.5px] font-semibold">{count}</span>}
      </Link>
    )
  }
  const groups: ReactNode[][] = [
    [link(BOARD), link(RUNS), <Fragment key="inbox">{inbox}</Fragment>],
    [link(KNOWLEDGE), link(CONNECTIONS)],
    [link(SETTINGS)],
  ]
  return (
    <nav aria-label={t('nav.main')} className="flex shrink-0 items-center gap-1">
      {groups.map((group, i) => (
        <Fragment key={i}>
          {i > 0 && <span aria-hidden className="mx-1 h-[18px] w-px bg-border" />}
          {group}
        </Fragment>
      ))}
    </nav>
  )
}
