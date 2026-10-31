import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/** The shortcuts of Inicio (phase 23): an emoji each, the name in a tooltip. */
export const SHORTCUTS = [
  { id: 'context', emoji: '📚', to: '/conocimiento?vista=documentos' },
  { id: 'skills', emoji: '🧩', to: '/conocimiento?vista=skills' },
  { id: 'mcps', emoji: '🔌', to: '/conexiones' },
  { id: 'board', emoji: '📋', to: '/tablero' },
  { id: 'runs', emoji: '▶️', to: '/ejecuciones' },
  { id: 'settings', emoji: '⚙️', to: '/ajustes' },
] as const

export function HomeShortcuts() {
  const { t } = useTranslation()
  return (
    <nav aria-label={t('home.shortcuts.label')} className="-mt-3 flex flex-wrap gap-2.5">
      {SHORTCUTS.map(({ id, emoji, to }) => (
        <Tooltip key={id}>
          <TooltipTrigger asChild>
            <Link
              to={to}
              aria-label={t(`home.shortcuts.${id}`)}
              className="grid size-11 place-items-center rounded-full border border-sep text-[20px] shadow-card transition-transform bg-card-grad hover:-translate-y-0.5 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span aria-hidden>{emoji}</span>
            </Link>
          </TooltipTrigger>
          <TooltipContent side="bottom">{t(`home.shortcuts.${id}`)}</TooltipContent>
        </Tooltip>
      ))}
    </nav>
  )
}
